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

import gpt
import cgpt

def orthogonalize(w,basis,ips=None):
    for j, v in enumerate(basis):
        ip=gpt.innerProduct(v,w)
        w -= ip*v
        if ips is not None:
            ips[j]=ip

def linear_combination(r,basis,Qt):
    assert(len(basis[0].v_obj) == len(r.v_obj))
    for i in r.otype.v_idx:
        cgpt.linear_combination(r.v_obj[i],basis,Qt,i)

def rotate(basis,Qt,j0,j1,k0,k1):
    for i in basis[0].otype.v_idx:
        cgpt.rotate(basis,Qt,j0,j1,k0,k1,i)

def qr_decomp(lmd,lme,Nk,Nm,Qt,Dsh,kmin,kmax):
    return cgpt.qr_decomp(lmd,lme,Nk,Nm,Qt,Dsh,kmin,kmax)
