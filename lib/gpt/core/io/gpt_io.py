#
#    GPT - Grid Python Toolkit
#    Copyright (C) 2020  Christoph Lehner (christoph.lehner@ur.de, https://github.com/lehner/gpt)
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License along
#    with this program; if not, write to the Free Software Foundation, Inc.,
#    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
import cgpt, gpt, os, io, numpy, sys, fnmatch, glob, math

# get local dir an filename
def get_local_name(root, cv):
    if cv.rank < 0:
        return None,None
    ntotal=cv.ranks
    rank=cv.rank
    dirs=32
    nperdir = ntotal // dirs
    if nperdir < 1:
        nperdir=1
    dirrank=rank//nperdir
    directory = "%s/%2.2d" % (root,dirrank)
    filename="%s/%10.10d.field" % (directory,rank)
    return directory,filename

# gpt io class
class gpt_io:
    def __init__(self, root, params, write):
        self.root = root
        self.params = params
        if not "grids" in self.params:
            self.params["grids"] = {}
        else:
            if type(self.params["grids"]) == gpt.grid:
                self.params["grids"] = [ self.params["grids"] ]
            self.params["grids"] = dict([ (g.describe(),g) for g in self.params["grids"] ])
        self.verbose = gpt.default.is_verbose("io")

        if gpt.rank() == 0:
            os.makedirs(self.root, exist_ok=True)
            if write:
                self.glb = gpt.FILE(root + "/global","wb")
                for f in glob.glob("%s/??/*.field" % self.root):
                    os.unlink(f)
            else:
                self.glb = gpt.FILE(root + "/global","r+b")
        else:
            self.glb = None

        self.loc = {}
        self.pos = {}
        self.loc_desc = ""

        # now sync since only root has created directory
        gpt.barrier()

    def __del__(self):
        self.close()

    def close_views(self):
        for f in self.loc:
            if not self.loc[f] is None:
                self.loc[f].close()
        self.loc={}
        self.pos={}
        self.loc_desc = ""

    def close_global(self):
        if not self.glb is None:
            self.glb.close()
            self.glb = None

    def close(self):
        self.close_global()
        self.close_views()

    def open_view(self, cv, write): # this should also cache positions
        dn,fn=get_local_name(self.root,cv)
        loc_desc = cv.describe() + "/" + ("Write" if write  else "Read")

        if loc_desc != self.loc_desc:
            self.close_views()
            self.loc_desc = loc_desc
            if self.verbose:
                gpt.message("Switching view to %s" % self.loc_desc)

        if not fn in self.loc:
            if write and not dn is None:
                os.makedirs(dn, exist_ok=True)
            self.loc[fn]=gpt.FILE(fn,"a+b" if write else "r+b") if not fn is None else None
            self.pos[fn]=gpt.coordinates(cv)

        #print("Rank %d (%s) processes %s" % (gpt.rank(),gpt.hostname,fn))
        #sys.stdout.flush()
        return self.loc[fn],self.pos[fn]

    def views_for_node(self,cv,grid):
        # need to have same length on each node but can have None entry if node does not participate
        grid_rank=grid.cartesian_rank()
        grid_stride=grid.Nprocessors
        views_per_node=int(math.ceil(cv.ranks / grid.Nprocessors))

        # number of writer groups
        ngroups=int(math.ceil(cv.ranks / gpt.default.nwriter))

        # first group
        views=[]
        for igroup in range(ngroups):
            for idx in range(views_per_node):
                iview=grid_rank + idx*grid_stride
                if iview % ngroups == igroup and iview < cv.ranks:
                    iv=iview
                else:
                    iv=None
                views.append(iv)
        return views


    def write_lattice(self, ctx, l):
        g=l.grid
        tag=(ctx + "\0").encode("utf-8")
        ntag=len(tag)
        nd=len(g.gdimensions)

        # create cartesian view for writing
        if "mpi" in self.params:
            mpi=self.params["mpi"]
        else:
            mpi=g.mpi
        cv0=gpt.cartesian_view(-1,mpi,g.gdimensions)

        # file positions
        pos=numpy.array([ 0 ] * cv0.ranks,dtype=numpy.uint64)

        # describe
        res=g.describe() + " " + cv0.describe() + " " + l.describe()

        # find tasks for my node
        views_for_node=self.views_for_node(cv0,g)

        # performance
        dt_distr,dt_crc,dt_write=0.0,0.0,0.0
        #g.barrier()
        t0=gpt.time()
        szGB=0.0

        # need to write all views
        for iview in views_for_node:
            if not iview is None:
                cv=gpt.cartesian_view(iview,mpi,g.gdimensions)
                dt_write-=gpt.time()
                f,p=self.open_view(cv,True)
                dt_write+=gpt.time()
                pos[iview]=f.tell()
            else:
                f,p=self.open_view(cv0,True) # empty view
                cv=None
                assert(len(p) == 0)

            # all nodes are needed to communicate
            dt_distr-=gpt.time()
            mv=gpt.mview(l[p])
            dt_distr+=gpt.time()

            # write data
            if not cv is None:
                # description and data
                dt_crc-=gpt.time()
                crc=gpt.crc32(mv)
                dt_crc+=gpt.time()
                dt_write-=gpt.time()
                f.write(ntag.to_bytes(4,byteorder='little'))
                f.write(tag)
                f.write(crc.to_bytes(4,byteorder='little'))
                f.write(nd.to_bytes(4,byteorder='little'))
                for i in range(nd):
                    f.write(g.gdimensions[i].to_bytes(4,byteorder='little'))
                for i in range(nd):
                    f.write(( g.gdimensions[i] // g.ldimensions[i]).to_bytes(4,byteorder='little'))
                f.write(len(mv).to_bytes(8,byteorder='little'))
                f.write(mv)
                f.flush()
                dt_write+=gpt.time()
                szGB+=len(mv) / 1024.**3.

        t1=gpt.time()

        szGB=g.globalsum(szGB)
        if self.verbose and dt_crc != 0.0:
            gpt.message("Wrote %g GB at %g GB/s (%g GB/s for distribution, %g GB/s for checksum, %g GB/s for writing, %d views per node)" % 
                        (szGB,szGB/(t1-t0),szGB/dt_distr,szGB/dt_crc,szGB/dt_write,len(views_for_node)))
        g.globalsum(pos)
        return res + " " + " ".join([ "%d" % x for x in pos ])

    def read_lattice(self, a):
        g_desc=a[0]
        cv_desc=a[1]
        l_desc=a[2]
        filepos=[ int(x) for x in a[3:] ]

        # first find grid
        if not g_desc in self.params["grids"]:
            self.params["grids"][g_desc]=gpt.grid(g_cesc)
        g=self.params["grids"][g_desc]

        # create a cartesian view and lattice to load
        cv0=gpt.cartesian_view(-1,cv_desc,g.gdimensions)
        l=gpt.lattice(g,l_desc)

        # find tasks for my node
        views_for_node=self.views_for_node(cv0,g)

        # performance
        dt_distr,dt_crc,dt_read=0.0,0.0,0.0
        szGB=0.0
        t0=gpt.time()

        # need to load all views
        for iview in views_for_node:
            if not iview is None:
                cv=gpt.cartesian_view(iview,cv_desc,g.gdimensions)
                # read data
                dt_read-=gpt.time()
                f,pos=self.open_view(cv,False)
                f.seek(filepos[iview],0)
                ntag=int.from_bytes(f.read(4),byteorder='little')
                f.read(ntag) # not needed if index is present
                crc_exp=int.from_bytes(f.read(4),byteorder='little')
                nd=int.from_bytes(f.read(4),byteorder='little')
                f.read(8*nd) # not needed if index is present
                sz=int.from_bytes(f.read(8),byteorder='little')
                data=memoryview(f.read(sz))
                dt_read+=gpt.time()
                dt_crc-=gpt.time()
                crc_comp=gpt.crc32(data)
                dt_crc+=gpt.time()
                assert(crc_comp == crc_exp)
                sys.stdout.flush()
                szGB+=len(data) / 1024.**3.
            else:
                f,pos=self.open_view(cv0,False) # empty view
                assert(len(pos) == 0)
                data=None
            dt_distr-=gpt.time()
            l[pos]=data
            dt_distr+=gpt.time()

        t1=gpt.time()

        szGB=g.globalsum(szGB)
        if self.verbose and dt_crc != 0.0:
            gpt.message("Read %g GB at %g GB/s (%g GB/s for distribution, %g GB/s for checksum, %g GB/s for reading, %d views per node)" % 
                        (szGB,szGB/(t1-t0),szGB/dt_distr,szGB/dt_crc,szGB/dt_read,len(views_for_node)))

        # TODO:
        # split grid exposure, allow cgpt_distribute to be given a communicator
        # and take it in importexport.h, add debug info here
        # more benchmarks, useful to create a plan for cgpt_distribute and cache? immutable numpy array returned from coordinates, attach plan
        return l

    def write_numpy(self, a):
        if not self.glb is None:
            pos=self.glb.tell()
            buf=io.BytesIO()
            numpy.save(buf,a, allow_pickle=False)
            mv=memoryview(buf.getvalue())
            crc=gpt.crc32(mv)
            self.glb.write(crc.to_bytes(4,byteorder='little'))
            self.glb.write(mv)
            return pos,self.glb.tell()
        return 0,0

    def read_numpy(self, start, end):
        if gpt.rank() == 0:
            self.glb.seek(start,0)
            crc32_compare=int.from_bytes(self.glb.read(4),byteorder='little')
            data=self.glb.read(end - start - 4)
        else:
            data=None
            crc32_compare=None
        data=gpt.broadcast(0,data)
        crc32_computed=gpt.crc32(memoryview(data))
        if not crc32_compare is None:
            assert(crc32_computed == crc32_compare)
        return numpy.load(io.BytesIO(data))

    def create_index(self, f, ctx, objs):
        if type(objs) == dict:
            f.write("{\n")
            for x in objs:
                f.write(x.encode("unicode_escape").decode("utf-8") + "\n")
                self.create_index(f,"%s/%s" % (ctx,x),objs[x])
            f.write("}\n")
        elif type(objs) == list:
            f.write("[\n")
            for i,x in enumerate(objs):
                self.create_index(f,"%s/%d" % (ctx,i),x)
            f.write("]\n")
        elif type(objs) == float:
            f.write("float %.16g\n" % objs)
        elif type(objs) == int:
            f.write("int %d\n" % objs)
        elif type(objs) == str:
            f.write("str " + objs.encode("unicode_escape").decode("utf-8") + "\n")
        elif type(objs) == complex:
            f.write("complex %.16g %.16g\n" % (objs.real,objs.imag))
        elif type(objs) == numpy.ndarray:
            f.write("array %d %d\n" % self.write_numpy(objs))
        elif type(objs) == gpt.lattice:
             f.write("lattice %s\n" % self.write_lattice(ctx,objs))
        else:
            assert(0)

    def keep_context(self, ctx):
        if not "paths" in self.params:
            return True
        paths=self.params["paths"]
        if type(paths) == str:
            paths=[ paths ]
        return (sum([ 1 if fnmatch.fnmatch(ctx,p) else 0 for p in paths ]) != 0)

    def read_index(self, p, ctx = ""):
        cmd=p.cmd()
        if cmd == "{":
            p.skip()
            res={}
            while True:
                cmd=p.cmd()
                if cmd == "}":
                    p.skip()
                    break
                key=p.get_str(0)
                res[key]=self.read_index(p,ctx + "/" + key)
            return res
        elif cmd == "[":
            p.skip()
            res=[]
            while True:
                cmd=p.cmd()
                if cmd == "]":
                    p.skip()
                    break
                res.append(self.read_index(p,ctx + ("/%d" % len(res))))
            return res
        elif cmd == "int":
            return int(p.get()[1])
        elif cmd == "float":
            return float(p.get()[1])
        elif cmd == "complex":
            a=p.get()
            return complex(float(a[1]),float(a[2]))
        elif cmd == "str":
            return p.get_str(1)
        elif cmd == "array":
            a=p.get() # array start end
            if not self.keep_context(ctx):
                return None
            return self.read_numpy(int(a[1]),int(a[2]))
        elif cmd == "lattice":
            a=p.get()
            if not self.keep_context(ctx):
                return None
            return self.read_lattice(a[1:])
        else:
            assert(0)


class index_parser:
    def __init__(self, lines):
        self.lines = lines
        self.line = 0

    def peek(self):
        return self.lines[self.line].split(" ")

    def get_str(self, i):
        return (" ".join(self.get()[i:])).encode("utf-8").decode("unicode_escape")

    def cmd(self):
        return self.peek()[0]

    def skip(self):
        self.line+=1

    def get(self):
        r=self.peek()
        self.skip()
        return r

    
def save(filename, objs, params):

    t0=gpt.time()

    # create io
    x=gpt_io(filename,params,True)

    # create index
    f=io.StringIO("")
    x.create_index(f,"",objs)
    mvidx=memoryview(f.getvalue().encode("utf-8"))

    # write index to fs
    index_crc=gpt.crc32(mvidx)
    if gpt.rank() == 0:
        open(filename + "/index","wb").write(mvidx)
        open(filename + "/index.crc32","wt").write("%X\n" % index_crc)

    # close
    x.close()

    # goodbye
    if x.verbose:
        t1=gpt.time()
        gpt.message("Completed writing %s in %g s" % (filename,t1-t0))


def load(filename, *a):

    # first check if this is right file format
    if not os.path.exists(filename + "/index.crc32"):
        raise NotImplementedError()

    # parameters
    if len(a) == 0:
        params={}
    else:
        params=a[0]

    # timing
    t0=gpt.time()

    # create io
    x=gpt_io(filename,params,False)

    # read index
    idx=open(filename + "/index","rb").read()
    crc_expected=int(open(filename + "/index.crc32","rt").read(),16)
    crc_computed=gpt.crc32(memoryview(idx))
    assert(crc_expected == crc_computed)

    p=index_parser(idx.decode("utf-8","strict").split("\n"))
    res=x.read_index(p)

    # close
    x.close()

    # goodbye
    if x.verbose:
        t1=gpt.time()
        gpt.message("Completed reading %s in %g s" % (filename,t1-t0))

    return res