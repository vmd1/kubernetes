import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import sync  # noqa: E402


def test_copies_in_place_keeps_the_inode_and_is_idempotent(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.write_text("restrictions:\n  - name: a\n")
    assert sync.sync(str(src), str(dst)) is True
    inode = os.stat(dst).st_ino
    src.write_text("restrictions: []\n")
    assert sync.sync(str(src), str(dst)) is True and os.stat(dst).st_ino == inode
    assert dst.read_text() == "restrictions: []\n"
    assert sync.sync(str(src), str(dst)) is False


def test_a_shorter_file_is_truncated_not_left_with_a_tail(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.write_text("restrictions:\n" + "  - name: long\n" * 20)
    sync.sync(str(src), str(dst))
    src.write_text("restrictions: []\n")
    sync.sync(str(src), str(dst))
    assert dst.read_text() == "restrictions: []\n"


def test_missing_or_empty_source_means_deny_all(tmp_path):
    dst = tmp_path / "dst"
    sync.sync(str(tmp_path / "nope"), str(dst))
    assert dst.read_text() == sync.DENY_ALL
    src = tmp_path / "src"
    src.write_text("restrictions:\n  - name: a\n")
    sync.sync(str(src), str(dst))
    src.write_text("  \n")
    sync.sync(str(src), str(dst))
    assert dst.read_text() == sync.DENY_ALL
