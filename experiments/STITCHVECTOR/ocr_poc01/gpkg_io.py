"""Read-only GPKG geometry access with sqlite3 + shapely (no GDAL). Opens files with mode=ro."""
import sqlite3, struct
import shapely

ENV = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def _wkb(blob):
    flags = blob[3]; return shapely.from_wkb(bytes(blob[8 + ENV[(flags >> 1) & 7]:]))


def layer(path, table):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    gcol = c.execute("select column_name from gpkg_geometry_columns where table_name=?", (table,)).fetchone()[0]
    cols = [r[1] for r in c.execute(f"pragma table_info({table})")]
    out = []
    for row in c.execute(f"select * from {table}"):
        d = dict(zip(cols, row)); g = d.pop(gcol); d["geometry"] = _wkb(g) if g else None; out.append(d)
    c.close(); return out
