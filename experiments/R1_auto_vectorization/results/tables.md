## Synthetic suite: overall (mean, 95% case-bootstrap CI)

| method | mIoU | object F1 | contact F1 (from areas) | fault-candidate F1 | all-lines F1 | all-lines P | all-lines R | runtime s |
|---|---|---|---|---|---|---|---|---|
| legacy_stratigraphy | 0.609 [0.41, 0.80] (n=14) | 0.122 [0.08, 0.17] (n=14) | 0.373 [0.22, 0.54] (n=14) | — | — | — | — | 2.234 [2.02, 2.50] (n=14) |
| legacy_boundary | — | — | — | — | 0.092 [0.05, 0.13] (n=14) | 0.535 [0.35, 0.71] (n=14) | 0.053 [0.03, 0.08] (n=14) | 6.878 [1.70, 13.80] (n=14) |
| legend_nearest_color | 0.857 [0.78, 0.93] (n=15) | 0.619 [0.46, 0.78] (n=15) | 0.785 [0.66, 0.91] (n=15) | 0.524 [0.42, 0.64] (n=15) | 0.802 [0.68, 0.92] (n=15) | 0.754 [0.60, 0.91] (n=15) | 0.939 [0.92, 0.96] (n=15) | 0.588 [0.51, 0.71] (n=15) |
| legend_rf | 0.861 [0.78, 0.94] (n=15) | 0.658 [0.49, 0.81] (n=15) | 0.811 [0.69, 0.92] (n=15) | 0.584 [0.49, 0.67] (n=15) | 0.824 [0.71, 0.93] (n=15) | 0.785 [0.64, 0.93] (n=15) | 0.941 [0.93, 0.96] (n=15) | 0.921 [0.88, 0.98] (n=15) |
| legend_rf_selftrain | 0.874 [0.80, 0.94] (n=15) | 0.681 [0.51, 0.84] (n=15) | 0.827 [0.71, 0.94] (n=15) | 0.656 [0.57, 0.74] (n=15) | 0.831 [0.72, 0.93] (n=15) | 0.791 [0.64, 0.93] (n=15) | 0.943 [0.93, 0.96] (n=15) | 1.678 [1.55, 1.91] (n=15) |
| legend_rf_selftrain+sam2 | 0.877 [0.80, 0.94] (n=15) | 0.706 [0.54, 0.86] (n=15) | 0.820 [0.70, 0.94] (n=15) | — | — | — | — | 3.449 [2.64, 4.40] (n=15) |

## Synthetic suite: by variant (mean of 3 seeds) — mIoU / object F1 / all-lines F1

| variant | legacy_stratigraphy | legacy_boundary | legend_nearest_color | legend_rf | legend_rf_selftrain | legend_rf_selftrain+sam2 |
|---|---|---|---|---|---|---|
| clean | 0.922 / 0.205 / — | — / — / 0.149 | 0.964 / 0.898 / 0.977 | 0.964 / 0.910 / 0.978 | 0.972 / 0.968 / 0.983 | 0.972 / 0.968 / — |
| hillshade | 0.018 / 0.000 / — | — / — / 0.048 | 0.591 / 0.089 / 0.394 | 0.600 / 0.103 / 0.422 | 0.654 / 0.138 / 0.467 | 0.667 / 0.157 / — |
| near_color | 0.943 / 0.234 / — | — / — / 0.198 | 0.970 / 0.887 / 0.977 | 0.971 / 0.907 / 0.976 | 0.973 / 0.937 / 0.981 | 0.973 / 0.937 / — |
| scan_jpeg | 0.347 / 0.048 / — | — / — / 0.049 | 0.817 / 0.433 / 0.704 | 0.824 / 0.560 / 0.790 | 0.826 / 0.570 / 0.772 | 0.827 / 0.638 / — |
| thick_ink | 0.725 / 0.099 / — | — / — / 0.000 | 0.942 / 0.788 / 0.959 | 0.944 / 0.809 / 0.952 | 0.945 / 0.790 / 0.953 | 0.946 / 0.831 / — |

## Confidence signals (UNCALIBRATED) on synthetic suite

| method | AUROC(region mean margin → object correct) | error px captured by top-10% tiles | by top-20% tiles |
|---|---|---|---|
| legend_nearest_color | 0.786 [0.70, 0.87] (n=15) | 0.185 [0.16, 0.22] (n=15) | 0.313 [0.26, 0.37] (n=15) |
| legend_rf | 0.875 [0.81, 0.93] (n=15) | 0.239 [0.19, 0.29] (n=15) | 0.377 [0.32, 0.43] (n=15) |
| legend_rf_selftrain | 0.827 [0.76, 0.89] (n=14) | 0.208 [0.17, 0.25] (n=15) | 0.358 [0.30, 0.42] (n=15) |

## AUTO_RETRY variant selection (synthetic, mIoU per case)

| case | base | shade-invariant | picked by mean margin | oracle |
|---|---|---|---|---|
| clean_s0 | 0.974 | 0.975 | shadeinv | shadeinv |
| clean_s1 | 0.969 | 0.971 | base | shadeinv |
| clean_s2 | 0.974 | 0.975 | shadeinv | shadeinv |
| hillshade_s0 | 0.674 | 0.903 | base | shadeinv |
| hillshade_s1 | 0.664 | 0.848 | shadeinv | shadeinv |
| hillshade_s2 | 0.625 | 0.774 | base | shadeinv |
| near_color_s0 | 0.974 | 0.977 | shadeinv | shadeinv |
| near_color_s1 | 0.971 | 0.971 | base | base |
| near_color_s2 | 0.974 | 0.974 | base | base |
| scan_jpeg_s0 | 0.963 | 0.865 | base | base |
| scan_jpeg_s1 | 0.932 | 0.738 | base | base |
| scan_jpeg_s2 | 0.583 | 0.788 | shadeinv | shadeinv |
| thick_ink_s0 | 0.953 | 0.960 | base | shadeinv |
| thick_ink_s1 | 0.955 | 0.958 | shadeinv | shadeinv |
| thick_ink_s2 | 0.928 | 0.930 | base | shadeinv |
| **mean** | 0.8742 | 0.9071 | 0.9006 | 0.9265 |

Selector agreed with oracle in 10/15 cases.

## Real maps (no full ground truth): observations

| map | swatches detected | legacy polygons | legacy unlabeled share | new regions | new classes used | new low-margin share | legacy s | new s |
|---|---|---|---|---|---|---|---|---|
| gm2_roi | 33 | 65 | 0.364 | 251 | 28 | 0.152 | 12.1 | 9.8 |
| u2 | 12 | 5 | 0.962 | 138 | 11 | 0.081 | 1.0 | 1.2 |
| u3 | 14 | 8 | 0.942 | 223 | 14 | 0.026 | 3.4 | 3.2 |
| u1 | 11 | 4 | 0.983 | 96 | 8 | 0.347 | 1.1 | 0.9 |
