import pytest
from voicetype.textproc import clean, is_noise, HALLUCINATIONS


class TestClean:
    def test_strips_whisper_leading_space(self):
        assert clean(" hello world") == "hello world"

    def test_collapses_internal_whitespace(self):
        assert clean("hello   \n  world") == "hello world"

    def test_preserves_code_switched_text(self):
        assert clean(" 把这个 function 重构一下") == "把这个 function 重构一下"

    def test_does_not_space_out_cjk(self):
        assert clean("今天天气很好") == "今天天气很好"

    def test_empty_input_yields_empty(self):
        assert clean("") == ""
        assert clean("   \n ") == ""

    def test_halfwidth_conversion_off_by_default(self):
        assert clean("你好，世界。") == "你好，世界。"

    def test_halfwidth_conversion_when_enabled(self):
        assert clean("你好，世界。", halfwidth=True) == "你好, 世界."

    def test_halfwidth_leaves_ascii_untouched(self):
        assert clean("a, b. c?", halfwidth=True) == "a, b. c?"

    def test_halfwidth_converts_cjk_question_and_colon(self):
        assert clean("为什么？因为：这样", halfwidth=True) == "为什么? 因为: 这样"

    def test_halfwidth_does_not_double_space(self):
        assert clean("好，  好", halfwidth=True) == "好, 好"


class TestIsNoise:
    @pytest.mark.parametrize("text", sorted(HALLUCINATIONS))
    def test_known_hallucinations_are_noise(self, text):
        assert is_noise(text)

    def test_hallucination_detection_ignores_case_and_punctuation(self):
        assert is_noise("thank you")
        assert is_noise("  Thank you!  ")

    def test_empty_is_noise(self):
        assert is_noise("")
        assert is_noise("   ")

    def test_real_speech_is_not_noise(self):
        assert not is_noise("thank you for reviewing the pull request")
        assert not is_noise("把这个 function 重构一下")
        assert not is_noise("ok")

    def test_bare_punctuation_is_noise(self):
        assert is_noise("。")
        assert is_noise("...")
