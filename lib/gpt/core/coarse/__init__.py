#
#    GPT - Grid Python Toolkit
#    Copyright (C) 2020  Christoph Lehner (christoph.lehner@ur.de, https://github.com/lehner/gpt)
#                  2020  Daniel Richtmann (daniel.richtmann@ur.de)
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
import gpt, cgpt, sys, numpy

def create_links(A, fmat, basis):
    # NOTE: we expect the blocks in the basis vectors
    # to already be orthogonalized!

    # get grids
    f_grid = basis[0].grid
    c_grid = A[0].grid

    # directions/displacements we coarsen for
    dirs = [0, 1, 2, 3]  # TODO: for 5d, this needs += 1
    nstencil = 2 * len(dirs) + 1
    disp = +1
    selflink = nstencil - 1  # last one in the list
    hermitian = True  # for now, needs to be a param -> TODO

    # setup fields
    Mvr = [gpt.lattice(basis[0]) for i in range(nstencil)]  # (needed by current grid)
    Mvre, Mvro, tmp = (
        gpt.lattice(basis[0]),
        gpt.lattice(basis[0]),
        gpt.lattice(basis[0]),
    )
    oproj = gpt.complex(c_grid)
    selfproj = gpt.vcomplex(c_grid, len(basis))

    # setup masks
    onemask, blockevenmask, blockoddmask = (
        gpt.complex(f_grid),
        gpt.complex(f_grid),
        gpt.complex(f_grid),
    )
    dirmasks = [gpt.complex(f_grid) for d in dirs]

    # auxilliary stuff needed for masks
    onemask[:] = 1.0
    coor = gpt.coordinates(blockevenmask)
    block = numpy.array(f_grid.ldimensions) / numpy.array(c_grid.ldimensions)
    block_cb = coor[:, :] // block[:]

    # fill masks for sites within even/odd blocks
    gpt.make_mask(blockevenmask, numpy.sum(block_cb, axis=1) % 2 == 0)
    blockoddmask @= onemask - blockevenmask

    # fill masks for sites on forward borders of blocks
    dirmasks_np = coor[:, :] % block[:] == block[:] - 1
    [gpt.make_mask(dirmasks[d], dirmasks_np[:, d]) for d in dirs]

    for i, vr in enumerate(basis):
        # apply directional hopping terms
        # this triggers four comms -> TODO expose DhopdirAll from Grid
        # BUT problem with vector<Lattice<...>> in rhs
        [fmat.Mdir(Mvr[d], vr, d, disp) for d in dirs]

        # coarsen directional terms + write to link
        for d in dirs:
            for j, vl in enumerate(basis):
                gpt.block.maskedInnerProduct(oproj, dirmasks[d], vl, Mvr[d])
                A[d][:, :, :, :, j, i] = oproj[:]

        # fast diagonal term: apply full matrix to both block cbs separately and discard hops into other cb
        tmp @= (
            blockevenmask * fmat.M * vr * blockevenmask
            + blockoddmask * fmat.M * vr * blockoddmask
        )

        # coarsen diagonal term + write to link
        gpt.block.project(selfproj, tmp, basis)
        A[selflink][:, :, :, :, :, i] = selfproj[:, :, :, :, :]

    # communicate opposite links
    for d in dirs:
        dd = d + len(dirs)
        shift_disp = disp * -1
        if hermitian:
            A[dd] @= gpt.adj(gpt.cshift(A[d], d, shift_disp))
        else:
            # linktmp = ... # TODO internal index manipulation for coarse spin dofs
            A[dd] @= gpt.adj(gpt.cshift(linktmp, d, shift_disp))


def recreate_links(A, fmat, basis):
    create_links(A, fmat, basis)
