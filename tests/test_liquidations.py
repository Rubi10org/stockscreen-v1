import base64
import hashlib
import json
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from liquidations import LiquidationStore, WebSocket, normalize_event


def event(side='SELL',quantity='2',price='100',symbol='BTCUSDT'):
    return {'e':'forceOrder','E':int(time.time()*1000),'st':1,'o':{'s':symbol,'S':side,'ap':price,'z':quantity,'p':'999','q':'999','T':int(time.time()*1000)}}


class EventTests(unittest.TestCase):
    def test_sell_is_long_buy_is_short(self):
        self.assertEqual(normalize_event(event())['side'],'long')
        self.assertEqual(normalize_event(event('BUY'))['side'],'short')

    def test_uses_executed_average_and_filled_quantity(self):
        value=normalize_event(event())
        self.assertEqual(value['notional'],200)
        self.assertEqual(value['price'],100)

    def test_rejects_unfilled_and_wrong_contracts(self):
        self.assertIsNone(normalize_event(event(quantity='0')))
        self.assertIsNone(normalize_event(event(price='NaN')))
        raw=event();raw['st']=2
        self.assertIsNone(normalize_event(raw))
        self.assertIsNone(normalize_event(event(symbol='OTHERUSDT')))

    def test_sqlite_dedup_and_side_specific_zones(self):
        with tempfile.TemporaryDirectory() as directory:
            store=LiquidationStore(Path(directory)/'events.sqlite3')
            long=normalize_event(event());short=normalize_event(event('BUY'))
            store.add(long);store.add(long);store.add(short)
            zones=store.zones(['BTCUSDT'],0,int(time.time()*1000)+1000)
            self.assertEqual(len(zones),2)
            self.assertEqual(sum(z['notional'] for z in zones),400)
            self.assertTrue(all(z['snapshots']==1 for z in zones))
            self.assertTrue(all(z['low']<=100<=z['high'] for z in zones))
            self.assertEqual(store.zones(['ETHUSDT'],0,int(time.time()*1000)),[])
            store.connection.close()

    def test_query_time_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            store=LiquidationStore(Path(directory)/'events.sqlite3')
            value=normalize_event(event());store.add(value)
            self.assertEqual(store.zones(['BTCUSDT'],value['time']+1,value['time']+2),[])
            store.connection.close()


class FakeSocket:
    def __init__(self,data):
        self.data=data
        self.sent=[]
    def recv(self,count):
        out,self.data=self.data[:count],self.data[count:]
        return out
    def sendall(self,data):
        self.sent.append(data)


def frame(op,payload,final=True):
    size=len(payload)
    head=bytes([(128 if final else 0)|op])
    return head+(bytes([size]) if size<126 else bytes([126])+struct.pack('!H',size))+payload


class FrameTests(unittest.TestCase):
    def client(self,raw):
        client=object.__new__(WebSocket)
        client.sock=FakeSocket(raw)
        client.buffer=b''
        return client

    def test_fragmented_json_and_ping_pong(self):
        raw=json.dumps(event()).encode();half=len(raw)//2
        client=self.client(frame(1,raw[:half],False)+frame(9,b'ping')+frame(0,raw[half:]))
        result=next(client.messages())
        self.assertEqual(result['e'],'forceOrder')
        pong=client.sock.sent[0]
        self.assertEqual(pong[0],138)
        self.assertTrue(pong[1]&128)
        self.assertEqual(bytes(v^pong[2+i%4] for i,v in enumerate(pong[6:])),b'ping')

    def test_rejects_huge_frames(self):
        client=self.client(bytes([129,127])+struct.pack('!Q',2**30))
        with self.assertRaises(ConnectionError):
            next(client.messages())

class HandshakeTests(unittest.TestCase):
    def fake(self,valid=True):
        class HandshakeSocket(FakeSocket):
            def __init__(self):
                super().__init__(b'')
            def settimeout(self,value):
                self.timeout=value
            def close(self):
                self.closed=True
            def sendall(self,data):
                if data.startswith(b'GET '):
                    key=data.split(b'Sec-WebSocket-Key: ')[1].split(b'\r\n')[0]
                    accept=base64.b64encode(hashlib.sha1(key+b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest()) if valid else b'wrong'
                    self.data=b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+b'\r\n\r\n'
                super().sendall(data)
        return HandshakeSocket()

    def test_validates_handshake_and_uses_current_market_path(self):
        sock=self.fake()
        with patch('liquidations.socket.create_connection',return_value=sock),patch('liquidations.ssl.create_default_context') as context:
            context.return_value.wrap_socket.return_value=sock
            client=WebSocket()
        self.assertIn(b'/market/ws/!forceOrder@arr',sock.sent[0])
        self.assertEqual(sock.timeout,240)
        client.close()

    def test_rejects_invalid_server_accept_hash(self):
        sock=self.fake(False)
        with patch('liquidations.socket.create_connection',return_value=sock),patch('liquidations.ssl.create_default_context') as context:
            context.return_value.wrap_socket.return_value=sock
            with self.assertRaises(ConnectionError):
                WebSocket()
