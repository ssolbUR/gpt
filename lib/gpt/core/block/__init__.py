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
import gpt,cgpt,sys
from gpt.core.block.operator import operator

def grid(fgrid, nblock):
    assert(fgrid.nd == len(nblock))
    for i in range(fgrid.nd):
        assert(fgrid.gdimensions[i] % nblock[i] == 0)
    # coarse grid will always be a full grid
    return gpt.grid([ fgrid.gdimensions[i] // nblock[i] for i in range(fgrid.nd) ],fgrid.precision,gpt.full)

def project(coarse, fine, basis):
    cot=coarse.otype
    fot=fine.otype
    tmp=gpt.lattice(coarse)
    coarse[:]=0
    for j in fot.v_idx:
        for i in cot.v_idx:
            cgpt.block_project(tmp.v_obj[i],fine.v_obj[j],basis[cot.v_n0[i]:cot.v_n1[i]],j)
        coarse += tmp

def promote(coarse, fine, basis):
    cot=coarse.otype
    fot=fine.otype
    tmp=gpt.lattice(fine)
    fine[:]=0
    for i in cot.v_idx:
        for j in fot.v_idx:
            cgpt.block_promote(coarse.v_obj[i],tmp.v_obj[j],basis[cot.v_n0[i]:cot.v_n1[i]],j)
        fine += tmp

def orthonormalize(coarse_grid, basis):
    assert(type(coarse_grid) == gpt.grid)
    assert(len(basis[0].v_obj) == 1) # for now
    coarse_tmp=gpt.complex(coarse_grid)
    cgpt.block_orthonormalize(coarse_tmp.v_obj[0],basis)
