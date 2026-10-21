"""PR-08 partial: durable duplicate protection using PR-02 audit ledger.

Sender identity MUST be authenticated by a later control-plane/broker layer;
this transport neither authenticates workers nor delivers network messages.
"""
from __future__ import annotations
from dataclasses import asdict
from subagentbridge.domain.contracts import Message
from subagentbridge.storage.audit_ledger import AuditLedger

class DurableMessageBus:
    def __init__(self, ledger:AuditLedger, *, stream:str):
        if not stream:raise ValueError('run stream required')
        self.ledger=ledger
        self.stream=stream

    def enqueue(self, message:Message, *, active_task_id:str, active_dispatch_id:str)->bool:
        if not isinstance(message,Message):raise TypeError('Message contract required')
        if (message.task_id,message.dispatch_id)!=(active_task_id,active_dispatch_id):
            raise PermissionError('cross-dispatch or stale message denied')
        if message.from_principal=='*' or message.to_principal=='*':
            raise PermissionError('worker broadcast not available')
        if type(message.payload) is not str or len(message.payload.encode('utf-8')) > 65536:
            raise ValueError('message payload must be bounded UTF-8 text')
        # Race-free exact replay: the ledger checks the key and event contents
        # inside one SQLite IMMEDIATE transaction, including across processes.
        _event, created = self.ledger.append_once(
            stream=self.stream, idempotency_key='message:'+message.message_id,
            event_type='MESSAGE_QUEUED', payload=asdict(message))
        return created

    def ack(self, message_id:str, *, recipient_id:str)->bool:
        if not message_id or not recipient_id:raise ValueError('message and recipient required')
        events=self.ledger.read(stream=self.stream,reader_stream=self.stream)
        found=[x for x in events if x.event_type=='MESSAGE_QUEUED' and x.payload['message_id']==message_id]
        if len(found)!=1 or found[0].payload['to_principal']!=recipient_id:
            raise PermissionError('ack target mismatch')
        _event, created = self.ledger.append_once(
            stream=self.stream,idempotency_key=f'ack:{message_id}:{recipient_id}',
            event_type='MESSAGE_ACK',payload={'message_id':message_id,'recipient_id':recipient_id})
        return created
