"""Draw the rollout architecture and finite frontier directly in Python.
Requires Python 3.9+ and Matplotlib; these are explanatory graphs, not measurements.
"""
import argparse
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrowPatch

plt.rcParams.update({'font.family':'STIXGeneral', 'mathtext.fontset':'stix',
                     'font.size':9, 'pdf.fonttype':42, 'ps.fonttype':42,
                     'text.usetex':False, 'axes.unicode_minus':False})
CM = 1 / 2.54

class Drawing:
    def __init__(self, bounds):
        x0,y0,x1,y1 = bounds
        self.fig = plt.figure(figsize=((x1-x0)*CM,(y1-y0)*CM))
        self.ax = self.fig.add_axes([0,0,1,1], xlim=(x0,x1), ylim=(y0,y1))
        self.ax.set_aspect('equal'); self.ax.axis('off')
        self.nodes = {}
        self.labels = []

    def text(self,x,y,label,size=9,ha='center',va='center'):
        artist=self.ax.text(x,y,label,fontsize=size,ha=ha,va=va,
                            linespacing=1.15,clip_on=False,zorder=4)
        self.labels.append([artist,None])
        return artist

    def box(self,name,x,y,w,h,label,dashed=False,shape='rect',size=9):
        style = {'edgecolor':'black','facecolor':'white','linewidth':.55,
                 'linestyle':(0,(4,3)) if dashed else 'solid', 'zorder':2}
        if shape == 'diamond':
            obj = Polygon([(x-w/2,y),(x,y+h/2),(x+w/2,y),(x,y-h/2)],**style)
        elif shape == 'circle': obj = Circle((x,y),w/2,**style)
        else: obj = Rectangle((x-w/2,y-h/2),w,h,**style)
        self.ax.add_patch(obj); self.text(x,y,label,size)
        self.labels[-1][1]=(x-w/2,y-h/2,x+w/2,y+h/2)
        self.nodes[name] = (x,y,w,h,shape)

    def point(self,name,side):
        x,y,w,h,_ = self.nodes[name]
        return {'n':(x,y+h/2),'s':(x,y-h/2),'e':(x+w/2,y),
                'w':(x-w/2,y),'nw':(x-w/2,y+h/2),
                'ne':(x+w/2,y+h/2),'c':(x,y)}[side]

    def line(self,points,dashed=False):
        xs,ys=zip(*points)
        self.ax.plot(xs,ys,color='black',linewidth=.55,
                     linestyle=(0,(4,3)) if dashed else 'solid',zorder=1)

    def arrow(self,p,q,dashed=False,via=()):
        points=[p,*via,q]
        if via:self.line(points[:-1],dashed)
        self.ax.add_patch(FancyArrowPatch(points[-2],points[-1],
                         arrowstyle='-|>',mutation_scale=7.5,linewidth=.55,
                         color='black',shrinkA=0,shrinkB=0,
                         linestyle=(0,(4,3)) if dashed else 'solid',zorder=1))

    def edge(self,a,b,sa='s',sb='n',**kwargs):
        self.arrow(self.point(a,sa),self.point(b,sb),**kwargs)

    def frame(self,x,y,w,h):
        self.ax.add_patch(Rectangle((x,y),w,h,fill=False,edgecolor='black',
                                   linewidth=.55,linestyle=(0,(4,3)),zorder=0))

    def save(self,out,name):
        # Fixed physical canvas: do not enlarge or rasterize the scientific figure.
        self.fig.canvas.draw()
        renderer=self.fig.canvas.get_renderer()
        x0,x1=self.ax.get_xlim();y0,y1=self.ax.get_ylim()
        for artist,node in self.labels:
            b=artist.get_window_extent(renderer).transformed(self.ax.transData.inverted())
            if b.x0<x0-.02 or b.x1>x1+.02 or b.y0<y0-.02 or b.y1>y1+.02:
                raise ValueError(name+': clipped label '+repr(artist.get_text()))
            if node and (b.x0<node[0]-.02 or b.x1>node[2]+.02 or b.y0<node[1]-.02 or b.y1>node[3]+.02):
                raise ValueError(name+': label exceeds node '+repr(artist.get_text()))
        self.fig.savefig(out/(name+'.pdf'),format='pdf',
                         metadata={'Creator':'Python Matplotlib','Producer':None,
                                   'CreationDate':None,'ModDate':None})
        plt.close(self.fig)





def draw(out):
    d=Drawing((0,0,17.6,4.9))
    for name,x,y,w,h,label,shade in (
        ('manifest',1.65,4,2.6,.85,'contract\nmanifest',.84),
        ('planner',5.1,4,2.7,.85,'explicit-frontier\nplanner',.94),
        ('certificate',9,4,3,.85,'schedule or\nblocking witness',.84),
        ('checker',13.7,4,3,.85,'independent\nchecker',.94),
        ('proxy',4.35,2.5,3.2,.95,'session-aware\nRPC proxy',.94),
        ('controller',8.65,2.5,3.4,.95,'rollout controller\nand crash journal',.94),
        ('old',2.55,1.05,3,.85,'old service\npersistent state',.84),
        ('new',6.15,1.05,3,.85,'new service\npersistent state',.84)):
        d.box(name,x,y,w,h,label)
        d.ax.patches[-1].set_facecolor(str(shade))
    d.box('actions',14.1,2,4.65,2.15,
          'after checker acceptance:\nquiescence demonstration\nstate transform + verify\ndual write + replay guard\nretain pins and old replicas',dashed=True,size=8.5)
    for a,b in (('manifest','planner'),('planner','certificate'),('certificate','checker')):
        d.edge(a,b,sa='e',sb='w')
    d.edge('manifest','checker',sa='n',sb='n',via=((1.65,4.66),(13.7,4.66)))
    d.edge('checker','controller',sa='s',sb='ne')
    d.edge('controller','proxy',sa='w',sb='e')
    d.edge('controller','actions',sa='e',sb='w')
    d.edge('proxy','old',sa='s',sb='n')
    d.edge('proxy','new',sa='s',sb='n')
    d.edge('old','new',sa='s',sb='s',via=((2.55,.21),(6.15,.21)))
    d.text(4.35,.23,'transform + load',size=8,va='bottom').set_bbox(dict(facecolor='white',edgecolor='none',pad=.5))
    d.save(out,'architecture')

    d=Drawing((0,0,8.35,2.95))
    positions={'OOO':(.55,2.45),'OBO':(2.35,2.45),'ONO':(4.15,2.45),
               'NOO':(.55,1.15),'NBO':(2.35,1.15),'NNO':(4.15,1.15),
               'NNB':(5.95,1.15),'NNN':(7.75,1.15)}
    for state,(x,y) in positions.items():
        viable=state[0]=='N'
        d.box(state,x,y,.76,.76,state,shape='circle',size=8)
        d.ax.patches[-1].set_facecolor('black' if viable else '.85')
        d.labels[-1][0].set_color('white' if viable else 'black')
    for chain,dashed in ((('OOO','OBO','ONO'),True),(('NOO','NBO','NNO','NNB','NNN'),False)):
        for a,b in zip(chain,chain[1:]):d.edge(a,b,sa='e',sb='w',dashed=dashed)
    d.text(.2,.4,'black: viable suffix\ngray: closed but nonviable',size=9,ha='left')
    d.save(out,'frontier')

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parent)
    out=parser.parse_args().output
    out.mkdir(parents=True,exist_ok=True)
    draw(out)
