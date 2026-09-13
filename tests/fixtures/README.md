# Test fixtures

- `en_refactor.wav` — espeak-ng, "please refactor this function for me".
  Regenerate: `espeak-ng -v en-us -s 150 -w /tmp/e.wav "please refactor this
  function for me" && ffmpeg -y -i /tmp/e.wav -ar 16000 -ac 1 en_refactor.wav`

- `mixed_zh_en.wav` — NOT generated. espeak-ng's Mandarin is too synthetic for
  Whisper to decode, so this must be a real human recording of
  "把这个 function 重构一下". Record it with:
      voicetype-record-fixture mixed_zh_en
  Tests needing it skip when it is absent.
