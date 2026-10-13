"""ทดสอบ app/common/domain_match.py"""
from common.domain_match import domain_condition

BS = chr(92)


def test_basic():
    sql, args = domain_condition("dl", "google.com")
    assert sql == "(dl.qname = %s OR dl.qname_rev LIKE %s)"
    assert args == ["google.com", "moc.elgoog.%"]


def test_normalize():
    _, args = domain_condition("dl", " .WWW.Example.COM. ")
    assert args == ["www.example.com", "moc.elpmaxe.www.%"]


def test_escape_wildcards():
    _, args = domain_condition("dl", "a_b%c.com")
    assert args[0] == "a_b%c.com"
    assert args[1] == "moc.c" + BS + "%b" + BS + "_a.%"


def test_escape_backslash():
    _, args = domain_condition("dl", "a" + BS + "b.com")
    assert args[1] == "moc.b" + BS * 2 + "a.%"


def test_no_prefix():
    sql, _ = domain_condition("", "x.com")
    assert sql == "(qname = %s OR qname_rev LIKE %s)"


def test_requires_dot_boundary():
    # notgoogle.com ต้องไม่ตรงกับ pattern ของ google.com
    _, args = domain_condition("dl", "google.com")
    assert not "moc.elgoogton".startswith(args[1][:-1])
