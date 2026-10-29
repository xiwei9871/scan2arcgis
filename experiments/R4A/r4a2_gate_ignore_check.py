import sys, numpy as np, torch, cv2
sys.path.insert(0,'experiments/R4A')
from r4a2_train import CFG, SEED, UNet, load_sheet, crop, to_batch, loss_fn
torch.manual_seed(SEED); rng=np.random.default_rng(SEED); dev=torch.device('mps')
m=UNet(1).to(dev); S=load_sheet(CFG['data_roles']['train'][0],rng)
opt=torch.optim.AdamW(m.parameters(),lr=1e-3,weight_decay=1e-4); items,_=crop(S,rng,'unit_boundary_pixel')
for _ in range(300):
    r,tb,ig,di,_=to_batch([items],dev); m.train(); l=loss_fn(m(r),tb,ig,di,'M1'); opt.zero_grad(); l.backward(); opt.step()
m.eval()
with torch.no_grad(): p=torch.sigmoid(m(to_batch([items],dev)[0])[0,0]).cpu().numpy()>0.5
g=items[4]>0; ign=items[2]>0; tgt=items[1]>0
print('M1 rerun: predicted px',int(p.sum()),'| share inside IGNORE_TRAIN band',round(float((p&ign).sum()/p.sum()),3),
      '| precision counting only non-ignored px',round(float((p&~ign&tgt).sum()/max((p&~ign).sum(),1)),3),'| recall of target band',round(float((p&tgt).sum()/tgt.sum()),3))
