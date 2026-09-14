import json
import pytest
from studio.opengame import OpenGameStream, OpenGameProtocolError


def result(**changes):
    return {'type':'result', 'session_id':'session', 'subtype':'success', 'is_error':False,
            'num_turns':2, 'permission_denials':[], 'usage':{'input_tokens':10,'output_tokens':5},
            'result':'SECRET: everything passed', **changes}


def wire(event):
    return (json.dumps(event, ensure_ascii=False)+'\n').encode()


def test_fragmented_utf8_tools_and_result_do_not_claim_gameplay_success():
    stream = OpenGameStream()
    events = [
        {'type':'system', 'session_id':'session', 'subtype':'init'},
        {'type':'assistant','session_id':'session','message':{'content':[
            {'type':'thinking','thinking':'SECRET'},
            {'type':'text','text':'修改游戏'},
            {'type':'tool_use','name':'mcp__workspace__edit','input':{'key':'SECRET'}}]}},
        {'type':'user','session_id':'session','message':{'content':[
            {'type':'tool_result','tool_use_id':'one','is_error':True,'content':'SECRET'}]}},
        result()]
    for byte in b''.join(map(wire,events)):
        stream.feed(bytes([byte]))
    report = stream.finish(0)
    assert report['execution_completed'] is True
    assert report['gameplay_verified'] is False
    assert report['tool_calls'] == ['mcp__workspace__edit'] and report['tool_errors'] == 1
    assert report['usage']['input_tokens'] == 10
    assert 'SECRET' not in str(report)


def test_text_claim_and_zero_exit_are_not_completion():
    stream = OpenGameStream()
    stream.feed(wire({'type':'assistant','session_id':'session','message':{'content':'success'}}))
    with pytest.raises(OpenGameProtocolError, match='没有返回最终结果'):
        stream.finish(0)


@pytest.mark.parametrize('changes', [
    {'is_error':True}, {'num_turns':True}, {'num_turns':21},
    {'usage':{'input_tokens':-1}}, {'permission_denials':None},
    {'parent_tool_use_id':'child'}, {'subtype':'maybe'}, {'session_id':None},
])
def test_invalid_final_results_rejected(changes):
    with pytest.raises(OpenGameProtocolError):
        OpenGameStream().feed(wire(result(**changes)))


@pytest.mark.parametrize('exit_code,event', [
    (1,result()), (0,result(permission_denials=[{'tool_input':'SECRET'}])),
    (0,result(subtype='error_during_execution',is_error=True)),
])
def test_failed_or_denied_execution_remains_unsuccessful(exit_code,event):
    stream = OpenGameStream();stream.feed(wire(event))
    report=stream.finish(exit_code)
    assert report['execution_completed'] is False and 'SECRET' not in str(report)


def test_mixed_sessions_and_post_result_events_rejected():
    stream=OpenGameStream()
    stream.feed(wire({'type':'system','session_id':'one'}))
    with pytest.raises(OpenGameProtocolError, match='其他会话'):
        stream.feed(wire(result()))
    stream=OpenGameStream();stream.feed(wire(result()))
    with pytest.raises(OpenGameProtocolError, match='最终结果后'):
        stream.feed(wire(result()))


def test_partial_final_line_and_output_limits():
    stream=OpenGameStream();stream.feed(wire(result()).rstrip(b'\n'))
    assert stream.finish(0)['execution_completed']
    with pytest.raises(OpenGameProtocolError, match='大小限制'):
        OpenGameStream(max_line=3).feed(b'xxxx')
    with pytest.raises(OpenGameProtocolError, match='大小限制'):
        OpenGameStream(max_bytes=3).feed(b'xxxx')
    with pytest.raises(OpenGameProtocolError, match='JSON'):
        OpenGameStream().feed(b'not json\n')
