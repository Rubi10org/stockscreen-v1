"""Public Binance USD-M liquidation snapshots; no credentials or dependencies."""
import base64
import hashlib
import json
import math
import os
import socket
import sqlite3
import ssl
import struct
import threading
import time
from pathlib import Path

SYMBOLS = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'FETUSDT', 'XRPUSDT'}
HOST = 'fstream.binance.com'
STREAM = '/market/ws/!forceOrder@arr'
MAX_FRAME = 1024 * 1024


def normalize_event(data):
    if not isinstance(data, dict) or data.get('e') != 'forceOrder':
        return None
    order = data.get('o', {})
    if order.get('s') not in SYMBOLS or int(data.get('st', order.get('st', 1))) != 1:
        return None
    if order.get('S') not in ('BUY', 'SELL'):
        return None
    price, quantity = float(order.get('ap', 0)), float(order.get('z', 0))
    timestamp = int(order.get('T', data.get('E', 0)))
    if not all(math.isfinite(n) and n > 0 for n in (price, quantity, timestamp)):
        return None
    # SELL closes a long; BUY closes a short. Never infer side from price direction.
    return {'symbol':order['s'], 'side':'long' if order['S']=='SELL' else 'short',
            'price':price, 'quantity':quantity, 'notional':price*quantity, 'time':timestamp}


class LiquidationStore:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.execute('CREATE TABLE IF NOT EXISTS events (symbol TEXT, side TEXT, price REAL, quantity REAL, notional REAL, timestamp INTEGER, UNIQUE(symbol,side,price,quantity,timestamp))')
        self.connection.execute('CREATE INDEX IF NOT EXISTS event_time ON events(timestamp)')
        self.connection.commit()

    def add(self, event):
        with self.lock:
            self.connection.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)', (event['symbol'],event['side'],event['price'],event['quantity'],event['notional'],event['time']))
            self.connection.execute('DELETE FROM events WHERE timestamp < ?', (int(time.time()*1000)-7*86400000,))
            self.connection.commit()

    def zones(self, symbols, start, end):
        if not symbols:
            return []
        with self.lock:
            self.connection.execute('DELETE FROM events WHERE timestamp < ?', (int(time.time()*1000)-7*86400000,))
            self.connection.commit()
            rows = self.connection.execute('SELECT symbol,side,price,notional,timestamp FROM events WHERE timestamp >= ? AND timestamp <= ? AND symbol IN ('+','.join('?' for _ in symbols)+')', [start,end]+list(symbols)).fetchall()
        bins = {}
        for symbol,side,price,notional,timestamp in rows:
            bucket = math.floor(math.log(price)/math.log1p(.002))
            key = (symbol,side,bucket)
            if key not in bins:
                low=math.exp(bucket*math.log1p(.002))
                bins[key]={'symbol':symbol,'side':side,'low':low,'high':low*1.002,'notional':0,'snapshots':0,'first':timestamp,'last':timestamp,'kind':'observed'}
            zone=bins[key]
            zone['notional']+=notional
            zone['snapshots']+=1
            zone['first']=min(zone['first'],timestamp)
            zone['last']=max(zone['last'],timestamp)
        result=[]
        for symbol in symbols:
            for side in ('long','short'):
                result.extend(sorted((z for z in bins.values() if z['symbol']==symbol and z['side']==side),key=lambda z:-z['notional'])[:3])
        return result


class WebSocket:
    """Minimal RFC6455 TLS client, including fragmented text and ping/pong."""
    def __init__(self):
        raw=socket.create_connection((HOST,443),timeout=15)
        try:
            self.sock=ssl.create_default_context().wrap_socket(raw,server_hostname=HOST)
            self.sock.settimeout(15)
            self.buffer=b''
            key=base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall(('GET '+STREAM+' HTTP/1.1\r\nHost: '+HOST+'\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: '+key+'\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            header=b''
            while b'\r\n\r\n' not in header:
                block=self.sock.recv(4096)
                if not block or len(header)>16384:
                    raise ConnectionError('WebSocket handshake failed')
                header+=block
            head,self.buffer=header.split(b'\r\n\r\n',1)
            lines=head.decode('latin1').split('\r\n')
            headers={k.lower().strip():v.strip() for line in lines[1:] if ':' in line for k,v in [line.split(':',1)]}
            expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if len(lines[0].split())<2 or lines[0].split()[1]!='101' or headers.get('sec-websocket-accept')!=expected:
                raise ConnectionError('Binance WebSocket rejected handshake: '+lines[0])
            self.sock.settimeout(240)
        except Exception:
            raw.close()
            if hasattr(self,'sock'):
                self.sock.close()
            raise

    def read(self, count):
        while len(self.buffer)<count:
            chunk=self.sock.recv(min(65536,count-len(self.buffer)))
            if not chunk:
                raise ConnectionError('WebSocket disconnected')
            self.buffer+=chunk
        result,self.buffer=self.buffer[:count],self.buffer[count:]
        return result

    def send_control(self, opcode, payload=b''):
        mask=os.urandom(4)
        self.sock.sendall(bytes([128|opcode,128|len(payload)])+mask+bytes(v^mask[i%4] for i,v in enumerate(payload)))

    def messages(self):
        fragments=b''
        while True:
            head=self.read(2)
            final,opcode,masked=bool(head[0]&128),head[0]&15,bool(head[1]&128)
            length=head[1]&127
            if length==126:
                length=struct.unpack('!H',self.read(2))[0]
            elif length==127:
                length=struct.unpack('!Q',self.read(8))[0]
            if length>MAX_FRAME or head[0]&112 or masked:
                raise ConnectionError('Unsupported WebSocket frame')
            payload=self.read(length)
            if opcode in (8,9,10) and (not final or length>125):
                raise ConnectionError('Invalid control frame')
            if opcode==8:
                raise ConnectionError('Binance closed WebSocket')
            if opcode==9:
                self.send_control(10,payload)
                continue
            if opcode==10:
                continue
            if opcode==1:
                fragments=payload
            elif opcode==0 and fragments:
                fragments+=payload
            else:
                raise ConnectionError('Unsupported message type')
            if len(fragments)>MAX_FRAME:
                raise ConnectionError('Message too large')
            if final:
                yield json.loads(fragments.decode('utf-8'))
                fragments=b''

    def close(self):
        self.sock.close()


class Collector:
    def __init__(self,path):
        self.store=LiquidationStore(path)
        self.stop=threading.Event()
        self.status={'connected':False,'startedAt':int(time.time()*1000),'lastEvent':None,'error':None,'source':'Binance USD-M forceOrder snapshots'}
        self.thread=None

    def start(self):
        if not self.thread:
            self.thread=threading.Thread(target=self.run,daemon=True)
            self.thread.start()

    def run(self):
        delay=2
        while not self.stop.is_set():
            ws=None
            try:
                ws=WebSocket()
                self.status.update(connected=True,error=None)
                delay=2
                for raw in ws.messages():
                    if self.stop.is_set():
                        return
                    payload=raw.get('data',raw) if isinstance(raw,dict) else raw
                    for item in payload if isinstance(payload,list) else [payload]:
                        try:
                            event=normalize_event(item)
                            if event:
                                self.store.add(event)
                                self.status['lastEvent']=event['time']
                        except (ValueError,TypeError,KeyError,OverflowError):
                            continue
            except Exception as error:
                self.status.update(connected=False,error=str(error)[:240])
            finally:
                if ws:
                    ws.close()
                self.status['connected']=False
            if self.stop.wait(delay):
                return
            delay=min(60,delay*2)

    def query(self,symbols,start,end):
        return {'status':dict(self.status),'zones':self.store.zones(symbols,start,end),'from':start,'to':end,'sampled':True}
