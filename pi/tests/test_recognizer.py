from watchman import topics
from watchman.recognizer import describe


def test_describe_jpeg_frame():
    assert describe(topics.FRAMES, b"\xff\xd8" + b"\x00" * 98) == "door/frames: jpeg frame, 100 bytes"


def test_describe_text_event():
    assert describe(topics.EVENT, b'{"ts": 1}') == 'door/event: {"ts": 1}'


def test_describe_binary_on_text_topic():
    assert describe(topics.EVENT, b"\xff\xfe\xfd") == "door/event: 3 bytes (binary)"


def test_describe_truncates_long_text():
    out = describe(topics.RESULT, b"x" * 500)
    assert out.endswith("...") and len(out) < 230
