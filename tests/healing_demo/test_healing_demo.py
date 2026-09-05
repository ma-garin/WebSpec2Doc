"""オートヒーリングの実証用。わざと 1 件だけ失敗させる。"""

from tests.healing_demo.demo_calc import add


def test_add():
    assert add(1, 2) == 3
