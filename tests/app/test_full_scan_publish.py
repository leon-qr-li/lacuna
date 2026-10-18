"""Show-notes table → list lines (item 26) edge cases found by the full scan of 2026-10-18."""
from lacuna_app.publish import has_table, untable


def test_an_escaped_pipe_stays_inside_its_cell():
    md = "| 片名 | 说明 |\n|---|---|\n| 《A\\|B》 | 好看 |\n"
    assert untable(md) == "- 《A|B》：好看\n"


def test_a_table_without_outer_pipes_is_converted_too():
    md = "片名 | 说明\n--- | ---\n《一部电影》 | 结尾\n\n正文"
    assert untable(md) == "- 《一部电影》：结尾\n\n正文" and has_table(md)


def test_text_with_a_pipe_above_a_plain_rule_is_not_a_table():
    md = "Leon | Pei 的对话\n---\n下一段"
    assert untable(md) == md and not has_table(md)


def test_the_usual_table_still_converts():
    md = "| 电影 | 导演 |\n| :-- | --: |\n| 《奥德赛》The Odyssey | 克里斯托弗·诺兰 |\n"
    assert untable(md) == "- 《奥德赛》The Odyssey：克里斯托弗·诺兰\n"
