import json, sys, math
src, dst = sys.argv[1], sys.argv[2]
NOMBRES = {"05":"Antioquia","08":"Atlántico","11":"Bogotá D.C.","13":"Bolívar","15":"Boyacá","17":"Caldas","18":"Caquetá","19":"Cauca","20":"Cesar","23":"Córdoba","25":"Cundinamarca","27":"Chocó","41":"Huila","44":"La Guajira","47":"Magdalena","50":"Meta","52":"Nariño","54":"Norte de Santander","63":"Quindío","66":"Risaralda","68":"Santander","70":"Sucre","73":"Tolima","76":"Valle del Cauca","81":"Arauca","85":"Casanare","86":"Putumayo","91":"Amazonas","94":"Guainía","95":"Guaviare","97":"Vaupés","99":"Vichada","88":"San Andrés y Providencia"}
TOL = 0.01  # grados (~1 km)
def perp(p, a, b):
    (x,y),(x1,y1),(x2,y2) = p,a,b
    dx,dy = x2-x1,y2-y1
    if dx==0 and dy==0: return math.hypot(x-x1,y-y1)
    t = max(0,min(1,((x-x1)*dx+(y-y1)*dy)/(dx*dx+dy*dy)))
    return math.hypot(x-(x1+t*dx), y-(y1+t*dy))
def dp(pts, tol):
    if len(pts) < 3: return pts
    dmax, idx = 0, 0
    for i in range(1,len(pts)-1):
        d = perp(pts[i], pts[0], pts[-1])
        if d > dmax: dmax, idx = d, i
    if dmax > tol:
        return dp(pts[:idx+1], tol)[:-1] + dp(pts[idx:], tol)
    return [pts[0], pts[-1]]
DESTINO = (-79.6, 12.6)  # recuadro en el Caribe, al noroccidente del continente
def ring(r, tol, scale=None):
    if scale:
        cx, cy, k = scale
        r = [[DESTINO[0]+(x-cx)*k, DESTINO[1]+(y-cy)*k] for x,y in r]
    out = dp([[round(x,4),round(y,4)] for x,y in r], tol)
    out = [[round(x,3),round(y,3)] for x,y in out]
    if out[0] != out[-1]: out.append(out[0])
    return out if len(out) >= 4 else None
sys.setrecursionlimit(100000)
d = json.load(open(src))
feats = []
for f in d["features"]:
    code = f["properties"]["DPTO"]
    g = f["geometry"]
    polys = g["coordinates"] if g["type"]=="MultiPolygon" else [g["coordinates"]]
    scale, tol = None, TOL
    if code == "88":
        # San Andrés es diminuto: se amplía x6 alrededor de su centro para que sea visible y clicable
        xs=[p[0] for poly in polys for p in poly[0]]; ys=[p[1] for poly in polys for p in poly[0]]
        scale=((min(xs)+max(xs))/2,(min(ys)+max(ys))/2,4); tol=0.0005
    newp = []
    for poly in polys:
        rings = [ring(r, tol, scale) for r in poly]
        if rings[0] is None: continue
        newp.append([r for r in rings if r])
    feats.append({"type":"Feature","properties":{"name":code,"codigo":code,"nombre":NOMBRES[code]},
                  "geometry":{"type":"MultiPolygon","coordinates":newp}})
json.dump({"type":"FeatureCollection","features":feats}, open(dst,"w"), separators=(",",":"), ensure_ascii=False)
print(len(feats), "features")
