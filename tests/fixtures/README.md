# Test fixtures

- `en_refactor.wav` — espeak-ng, "please refactor this function for me".
  Regenerate: `espeak-ng -v en-us -s 150 -w /tmp/e.wav "please refactor this
  function for me" && ffmpeg -y -i /tmp/e.wav -ar 16000 -ac 1 en_refactor.wav`

- `mixed_zh_en.wav` — NOT generated. espeak-ng's Mandarin is too synthetic for
  Whisper to decode, so this must be a real human recording. Say:

      这个 API 的 response 有点慢,需要加 cache

  Record it with `voicetype-record-fixture mixed_zh_en`; tests needing it skip
  when it is absent.

  Keep this phrase OUT of `initial_prompt`. Whisper will happily parrot a
  phrase it was primed with, which makes the test pass without proving the
  model can code-switch at all.
