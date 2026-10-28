#!/bin/bash
# R4-A Q3: register each Q1/Q2-passing sheet with the unchanged R2 tools, then run the
# fill-independent ink-line check. Outputs go to runs/r4a/<code>/ (git-ignored).
# Usage: experiments/R4A/register_all.sh CODE:YEAR [CODE:YEAR ...]
set -u
cd "$(dirname "$0")/../.."
P=.venv/bin/python; R2=experiments/R2_real_map
for cy in "$@"; do
  c=${cy%%:*}; y=${cy##*:}
  I=data/raw/gsj_r4a/GSJ_MAP_G050_${c}_${y}_200dpi.jpg; S=data/raw/gsj_r4a/norm/$c/shp; O=runs/r4a/$c
  mkdir -p $O
  B=$($P -c "import json;print(','.join(str(v) for v in json.load(open('data/raw/gsj_r4a/norm/$c/sheet_info.json'))['bounds_lonlat']))")
  $P $R2/gsj_frame.py $I $O/frame.json $B > $O/frame.log 2>&1; rf=$?
  if [ $rf -ne 0 ]; then echo "$c frame FAIL rc=$rf"; continue; fi
  $P $R2/gsj_register.py $I $O/frame.json $S $O/frame_reg.json > $O/register.log 2>&1; rr=$?
  if [ $rr -ne 0 ]; then echo "$c register FAIL rc=$rr"; continue; fi
  $P $R2/gsj_reg_independent.py $I $S $O/reg_independent.json frame_only=$O/frame.json colour_refined=$O/frame_reg.json > $O/reg_independent.log 2>&1
  echo "$c done rc=$?"
done
echo ALLDONE
