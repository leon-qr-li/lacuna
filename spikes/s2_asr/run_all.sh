#!/usr/bin/env bash
# Reproduce all S2 runs sequentially (CPU, 4 threads). Usage:
#   S2=/path/to/scratch ./run_all.sh
# Expects: $S2/venv (python), $S2/audio/{Leon,Pei}_900_1200.wav (16 kHz mono),
#          $S2/models/{silero_vad.onnx, sherpa-onnx-*, ct2-turbo, ct2-large-v3}
set -u
cd "$(dirname "$0")"
PY="$S2/venv/bin/python"; M="$S2/models"; O="$S2/out"; mkdir -p "$O"
for T in Leon Pei; do
  A="$S2/audio/${T}_900_1200.wav"
  $PY run_paraformer.py  --audio "$A" --models "$M" --out "$O/paraformer_$T.json"
  $PY run_sensevoice.py  --audio "$A" --models "$M" --out "$O/sensevoice_$T.json"
  $PY run_faster_whisper.py --audio "$A" --model "$M/ct2-turbo" --vad --out "$O/fw_turbo_vad_none_$T.json"
  $PY run_faster_whisper.py --audio "$A" --model "$M/ct2-turbo" --vad --prompt fillers --out "$O/fw_turbo_vad_fillers_$T.json"
  $PY run_faster_whisper.py --audio "$A" --model "$M/ct2-turbo" --out "$O/fw_turbo_novad_none_$T.json"
done
A="$S2/audio/Leon_900_1200.wav"
$PY run_paraformer.py --punct --audio "$A" --models "$M" --out "$O/paraformer_punct_Leon.json"
$PY run_sensevoice.py --itn   --audio "$A" --models "$M" --out "$O/sensevoice_itn_Leon.json"
$PY run_faster_whisper.py --audio "$A" --model "$M/ct2-large-v3" --vad --out "$O/fw_large-v3_vad_none_Leon.json"
$PY run_faster_whisper.py --audio "$A" --model "$M/ct2-large-v3" --vad --prompt fillers --out "$O/fw_large-v3_vad_fillers_Leon.json"
A="$S2/audio/Pei_900_1200.wav"
$PY run_faster_whisper.py --audio "$A" --model "$M/ct2-large-v3" --vad --out "$O/fw_large-v3_vad_none_Pei.json"
$PY run_faster_whisper.py --audio "$A" --model "$M/ct2-large-v3" --out "$O/fw_large-v3_novad_none_Pei.json"
echo ALLDONE
