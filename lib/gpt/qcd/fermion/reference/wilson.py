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
import gpt as g

class wilson:
    # M = sum_mu gamma[mu]*D[mu] + m0 - 1/2 sum_mu D^2[mu]
    # m0 + 4 = 1/2/kappa
    def __init__(self, U, params):

        if "mass" in params:
            assert(not "kappa" in params)
            self.kappa = 1./(params["mass"] + 4.)/2.
        else:
            self.kappa = params["kappa"]

        self.U = U
        self.Udag = [ g.eval(g.adj(u)) for u in U ]

    def Meooe(self, src, dst):
        assert(dst != src)
        dst[:]=0
        for mu in range(4):
            src_plus = self.U[mu]*g.cshift(src,mu,+1)
            dst += 1./2.*g.gamma[mu]*src_plus - 1./2.*src_plus

            src_minus = g.cshift(self.Udag[mu]*src,mu,-1)
            dst += -1./2.*g.gamma[mu]*src_minus - 1./2.*src_minus

    def Mooee(self, src, dst):
        assert(dst != src)
        dst @= 1./2.*1./self.kappa * src

    def M(self, src, dst):
        assert(dst != src)
        t=g.lattice(dst)
        self.Meooe(src,t)
        self.Mooee(src,dst)
        dst += t

    def G5M(self, src, dst):
        assert(dst != src)
        self.M(src,dst)
        dst @= g.gamma[5] * dst
