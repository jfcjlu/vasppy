#! /usr/bin/env python3 

import sys
import re
import string
import numpy as np
import argparse
import copy
import signal

# Restore SIGPIPE back to default action
# http://www.chiark.greenend.org.uk/ucgi/~cjwatson/blosxom/2009-07-02-python-sigpipe.html
signal.signal( signal.SIGPIPE, signal.SIG_DFL )

def parity( list ):
    '''Calculate the parity of a list of integers.

    Args:
        list (list): the list to calculate the parity of. 
    Returns:
        0 if the list contains an even number of odd elements;
        1 if the list contains an odd number of odd element.
    Raises:
        TypeError: if 'list' contains elements that are not integers.
    '''
    if not all( isinstance( item, int ) for item in list ):
        raise TypeError
    return( sum( list )%2 )

class Poscar:

    def __init__( self ):
        self.title = "Title"
        self.scaling = 1.0
        self.lattice = np.identity( 3 )
        self.atoms = [ 'A' ]
        self.atom_numbers = [ 1 ]
        self.coordinate_type = 'Direct'
        self.coordinates = np.array( [ [ 0.0, 0.0, 0.0 ] ] )
  
    def read_from( self, filename ):
        try:
            with open( filename ) as f:
                lines = f.readlines()
        except FileNotFoundError:
            print( "\"" + filename + "\" not found" ) 
            sys.exit( -2 )
        self.title = lines.pop(0).strip()
        self.scaling = float( lines.pop(0).strip() )
        self.lattice = np.array( [ [ float( e ) for e in lines.pop(0).split() ] for i in range( 3 ) ] )
        self.atoms = lines.pop(0).split()
        self.atom_numbers = [ int(element) for element in lines.pop(0).split() ]
        self.coordinate_type = lines.pop(0)
        self.coordinates = np.array( [ [ float( e ) for e in lines.pop(0).split()[0:3] ] for i in range( sum( self.atom_numbers ) ) ] )
        if self.coords_are_cartesian(): # Use direct coordinates internally
            self.coordinates = self.fractional_coordinates()
            self.coordinate_type = 'Direct'

    def in_bohr( self ):
        new_poscar = copy.deepcopy( self )
        bohr_to_angstrom = 0.529177211
        new_poscar.scaling *= bohr_to_angstrom
        new_poscar.lattice /= bohr_to_angstrom
        if new_poscar.coords_are_cartesian():
            new_poscar.coordinates /= bohr_to_angstrom
        return( new_poscar )

    def coords_are_fractional( self ):
        return re.match( r'\A[Dd]', self.coordinate_type )

    def coords_are_cartesian( self ):
        return not self.coords_are_fractional()

    def fractional_coordinates( self ):
        return ( self.coordinates if self.coords_are_fractional() else self.coordinates.dot( np.linalg.inv( self.lattice ) ) )

    def cartesian_coordinates( self ):
        return ( self.coordinates if self.coords_are_cartesian() else self.coordinates.dot( self.lattice ) )

    def coordinates_to_stdout( self, coordinate_type='Direct' ):
        coord_opts = { 'Direct'    : self.fractional_coordinates(), 
                       'Cartesian' : self.cartesian_coordinates() }
        try:
            [ print( ''.join( ['  % .10f' % element for element in row ] ) ) for row in coord_opts[ coordinate_type ] ]
        except KeyError: 
            raise Exception( 'Passed coordinate_type: ' + coordinate_type + '\nAccepted values: [ Direct | Cartesian ] ' )

    def labelled_coordinates_to_stdout( self, coordinate_type='Direct', label_pos='1' ):
        coord_opts = { 'Direct'    : self.fractional_coordinates(), 
                       'Cartesian' : self.cartesian_coordinates() } 
        if label_pos == 1:
            for ( row, label ) in zip( coord_opts[ coordinate_type ], self.labels() ):
                print( label.ljust(6) + ''.join( [ '  %.10f' % element for element in row ] ) )
        if label_pos == 4:
            for ( row, label ) in zip( coord_opts[ coordinate_type ], self.labels() ):
                print( ''.join( [ '  %.10f' % element for element in row ] ) + '  %.4s' % label )

    def output_coordinates_only( self, coordinate_type='Direct', label=None ):
        if label:
            self.labelled_coordinates_to_stdout( coordinate_type, label )
        else:
            self.coordinates_to_stdout( coordinate_type )

    def output( self, coordinate_type='Direct', label=None ):
        print( self.title )
        print( self.scaling )
        [ print( ''.join( ['   % .10f' % element for element in row ] ) ) for row in self.lattice ]
        # np.savetxt( sys.stdout.buffer, self.lattice, fmt='  %.4f' )
        # sys.stdout.flush()
        print( ' '.join( self.atoms ) )
        print( ' '.join( [ str(n) for n in self.atom_numbers ] ) )
        print( coordinate_type )
        self.output_coordinates_only( coordinate_type, label )

    def labels( self ):
        return( [ atom_name for ( atom_name, atom_number ) in zip( self.atoms, self.atom_numbers ) for __ in range( atom_number ) ] )

    def replicate( self, h, k, l, group=False ):
        lattice_scaling = np.array( [ h, k, l ], dtype=float )
        lattice_shift = np.reciprocal( lattice_scaling ) 
        new_poscar = Poscar()
        new_poscar.title = self.title
        new_poscar.scaling = self.scaling
        # print( lattice_scaling.dot( self.lattice ) )
        new_poscar.lattice = ( self.lattice.T * lattice_scaling ).T
        new_poscar.coordinate_type = self.coordinate_type
        new_coordinate_list = []
        cell_shift_indices = [ [a,b,c] for a in range(h) for b in range(k) for c in range(l) ]
        # generate grouped / ungrouped atom names and numbers for supercell
        if group:
            new_poscar.atoms = [ label + group for label in self.atoms for group in ('a','b') ]
            new_poscar.atom_numbers = [ int( num * h * k * l / 2 ) for num in self.atom_numbers for __ in ( 0, 1 )]
        else:
            new_poscar.atoms = self.atoms
            new_poscar.atom_numbers = [ num * h * k * l for num in self.atom_numbers ]
        # generate grouped / ungrouped atoms coordinates for supercell
        if group:
            for row in self.coordinates:
                pos_in_origin_cell = row / lattice_scaling
                for odd_even in ( 0, 1 ):
                    for ( a, b, c ) in [ cell_shift for cell_shift in cell_shift_indices if parity(cell_shift) == odd_even ]:
                        new_coordinate_list.append( [ pos_in_origin_cell + np.array( [ a, b, c ] * lattice_shift ) ][0].tolist() )
        else:
            for row in self.coordinates:
                pos_in_origin_cell = row / lattice_scaling
                for ( a, b, c ) in cell_shift_indices:
                    new_coordinate_list.append( [ pos_in_origin_cell + np.array( [ a, b, c ] * lattice_shift ) ][0].tolist() )
        new_poscar.coordinates = np.array( new_coordinate_list )
        return new_poscar        

def parse_command_line_arguments():
    # command line arguments
    parser = argparse.ArgumentParser( description='Manipulates VASP POSCAR files' )
    parser.add_argument( 'poscar', help="filename of the VASP POSCAR to be processed" )
    parser.add_argument( '-l', '--label', type=int, choices=[ 1, 4 ], help="label coordinates with atom name at position {1,4}" )
    parser.add_argument( '-c', '--coordinates-only', help='only output coordinates', action='store_true' )
    parser.add_argument( '-t', '--coordinate-type', type=str, choices=[ 'c', 'cartesian', 'd', 'direct' ], default='direct', help="specify coordinate type for output {(c)artesian|(d)irect} [default = (d)irect]" )
    parser.add_argument( '-g', '--group', help='group atoms within supercell', action='store_true' )
    parser.add_argument( '-s', '--supercell', type=int, nargs=3, metavar=( 'h', 'k', 'l' ), help='construct supercell by replicating (h,k,l) times along [a b c]' )
    parser.add_argument( '-b', '--bohr', action='store_true', help='assumes the input file is in Angstrom, and converts everything to bohr')
    args = parser.parse_args()
    return( args )

if __name__ == "__main__":
    args = parse_command_line_arguments()
    coordinate_types = { 'd' : 'Direct',
                         'direct' : 'Direct',
                         'c' : 'Cartesian',
                         'cartesian' : 'Cartesian' }
    coordinate_type = coordinate_types[ args.coordinate_type ]
    # initialise
    poscar = Poscar()
    # read POSCAR file
    poscar.read_from( args.poscar )
    if args.supercell: # generate supercell
        if args.group:
            # check that if grouping is switched on, we are asking for a supercell that allows a "3D-chequerboard" pattern.
            for (i,axis) in zip( args.supercell, range(3) ):
                if i%2==1 and i>1:
                    raise Exception( "odd supercell expansions != 1 are incompatible with automatic grouping" )
        poscar = poscar.replicate( *args.supercell, group=args.group )
    if args.bohr:
        poscar = poscar.in_bohr()
    # output to stdout
    if args.coordinates_only:
        poscar.output_coordinates_only( coordinate_type = coordinate_type, label = args.label )
    else:
        poscar.output( coordinate_type = coordinate_type, label = args.label )