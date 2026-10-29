#!/bin/sh
# R4-A2.2 post-training pipeline: M0 + M1/M2 inference on 15023/15041, unified evaluation, visuals,
# vector export + validation, China zero-shot. Run from experiments/R4A after both formal runs finished.
# Predictions/visuals/vectors stay local under runs/r4a2/r4a22/; metric JSONs go to experiments/R4A/r4a2_2/.
set -e
ML=../../.venv-ml/bin/python; GEO=../../.venv/bin/python
P=../../runs/r4a2/r4a22; J=r4a2_2; M=../../runs/r4a2/models
mkdir -p $P $J/eval $J/export
for c in 15023 15041; do
  $GEO r4a2_2_m0.py $c $P/$c/M0     # R1 needs scikit-learn (.venv); .venv-ml has none
  $ML r4a2_2_infer.py M1 $M/M1_formal/best.pt ../../runs/r4a2/$c/geotiff_rgb.png $P/$c/M1
  $ML r4a2_2_infer.py M2 $M/M2_formal/best.pt ../../runs/r4a2/$c/geotiff_rgb.png $P/$c/M2
  mkdir -p $P/$c/M2_oldseed $P/$c/M2_hybrid
  ln -sf ../M2/regions_M2_oldseed.npy $P/$c/M2_oldseed/regions_M2_oldseed.npy
  ln -sf ../M2/regions_M2_hybrid.npy $P/$c/M2_hybrid/regions_M2_hybrid.npy
  $ML r4a2_2_eval.py $c $P/$c/M0/regions_M0.npy $J/eval/${c}_M0.json
  $ML r4a2_2_eval.py $c $P/$c/M1/regions_M1.npy $J/eval/${c}_M1.json $P/$c/M1/prob.npy
  $ML r4a2_2_eval.py $c $P/$c/M2/regions_M2_oldseed.npy $J/eval/${c}_M2_oldseed.json $P/$c/M2/prob.npy
  $ML r4a2_2_eval.py $c $P/$c/M2/regions_M2_hybrid.npy $J/eval/${c}_M2_hybrid.json
  $ML r4a2_2_vis.py $c $P/$c $P/vis
  $GEO r4a2_2_export.py $c M0 $P/$c/M0/regions_M0.npy $P/export/$c/M0 $P/$c/M0/margin.npy margin
  $GEO r4a2_2_export.py $c M1 $P/$c/M1/regions_M1.npy $P/export/$c/M1 $P/$c/M1/prob.npy prob
  $GEO r4a2_2_export.py $c M2_oldseed $P/$c/M2/regions_M2_oldseed.npy $P/export/$c/M2_oldseed $P/$c/M2/prob.npy prob
  $GEO r4a2_2_export.py $c M2_hybrid $P/$c/M2/regions_M2_hybrid.npy $P/export/$c/M2_hybrid $P/$c/M2/prob.npy prob
  for m in M0 M1 M2_oldseed M2_hybrid; do
    $GEO validate_pixel_vectors.py $P/export/$c/$m/${c}_$m.gpkg $P/export/$c/$m/labels.npy 1.0 $J/export/${c}_${m}_validation.json
    cp $P/export/$c/$m/${c}_${m}_export_summary.json $J/export/
  done
done
$ML r4a2_2_china.py $M/M1_formal/best.pt $M/M2_formal/best.pt $P/china
cp $P/china/china_zero_shot.json $J/
cp $P/vis/*_vis_index.json $J/
echo ALL DONE
