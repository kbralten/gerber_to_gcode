#!/usr/bin/env python3
"""
Excellon Drill File to G-code Converter

This program reads Excellon drill files and generates G-code for CNC milling.
It supports both straight plunge drilling for small holes and spiral milling
for larger holes.
"""

import argparse
import math
import re
import sys
from typing import List, Tuple, Dict


class ExcellonToGcode:
    """Convert Excellon drill files to G-code for CNC milling."""

    def __init__(self, input_file: str, output_file: str, bit_size: float, 
                 drill_depth: float, feed_rate: float = 100.0, 
                 plunge_rate: float = 50.0, spindle_speed: int = 10000,
                 safe_height: float = 5.0, clearance_height: float = 2.0,
                 use_arcs: bool = False):
        """
        Initialize the converter.

        Args:
            input_file: Path to the Excellon drill file
            output_file: Path to write the G-code output
            bit_size: Diameter of the milling bit in mm (default 1mm)
            drill_depth: Depth to drill/mill in mm (default 2mm)
            feed_rate: XY movement feed rate in mm/min
            plunge_rate: Z plunge feed rate in mm/min
            spindle_speed: Spindle RPM
            safe_height: Safe Z height for rapid movements in mm
            clearance_height: Z clearance height above workpiece in mm
            use_arcs: Use G2/G3 arc moves instead of G1 line segments (default False)
        """
        self.input_file = input_file
        self.output_file = output_file
        self.bit_size = bit_size
        self.bit_radius = bit_size / 2.0
        self.drill_depth = drill_depth
        self.feed_rate = feed_rate
        self.plunge_rate = plunge_rate
        self.spindle_speed = spindle_speed
        self.safe_height = safe_height
        self.clearance_height = clearance_height
        self.use_arcs = use_arcs
        self.drill_holes: List[Tuple[float, float, float]] = []

    def parse_excellon_file(self):
        """Parse Excellon drill file and extract drill hole information."""
        try:
            with open(self.input_file, 'r') as f:
                lines = f.readlines()

            tools: Dict[str, float] = {}  # Tool number -> diameter in mm
            current_tool = None
            metric = True
            current_x = 0.0
            current_y = 0.0

            # Extract file format (e.g. ;FILE_FORMAT=4:4) and zero suppression mode
            int_digits = 4
            dec_digits = 4
            # Excellon header METRIC,LZ means leading zeros present, trailing zeros suppressed
            zero_mode = 'LZ'

            for line in lines:
                line = line.strip()

                # Skip empty lines and comments (except format comments)
                if not line or (line.startswith(';') and 'FILE_FORMAT' not in line):
                    continue

                # Header parsing - FILE_FORMAT
                if line.startswith(';FILE_FORMAT='):
                    try:
                        fmt = line.split('=')[1]
                        parts = fmt.split(':')
                        if len(parts) == 2:
                            int_digits = int(parts[0])
                            dec_digits = int(parts[1])
                    except Exception as e:
                        print(f"Warning: Could not parse FILE_FORMAT: {e}")

                # Unit mode
                if 'METRIC' in line:
                    metric = True
                elif 'INCH' in line:
                    metric = False

                # Zero suppression mode
                if 'LZ' in line:
                    zero_mode = 'LZ'
                elif 'TZ' in line:
                    zero_mode = 'TZ'

                # Tool definition: T01F00S00C0.3000 or T01C0.3000
                if line.startswith('T') and 'C' in line and not line.startswith('TYPE'):
                    match = re.match(r'T(\d+).*C([\d.]+)', line)
                    if match:
                        tool_num = 'T' + match.group(1)
                        diameter_str = match.group(2)
                        try:
                            diameter = float(diameter_str)
                            if not metric:
                                diameter *= 25.4  # Convert inches to mm
                            tools[tool_num] = diameter
                            print(f"Tool {tool_num}: {diameter:.4f} mm")
                        except ValueError:
                            print(f"Warning: Could not parse tool diameter: {diameter_str}")
                    continue

                # Tool selection (e.g. T01)
                if line.startswith('T') and 'C' not in line and len(line) <= 4:
                    current_tool = line
                    if current_tool in tools:
                        print(f"Selected tool {current_tool}")
                    continue

                # Coordinate lines start with X or Y
                if ((line.startswith('X') or line.startswith('Y')) 
                        and current_tool and current_tool in tools):
                    x_str = None
                    y_str = None

                    # Parse X and Y coordinates
                    if 'X' in line and 'Y' in line:
                        parts = line.split('Y')
                        x_str = parts[0][1:]  # Remove 'X'
                        y_str = parts[1]
                    elif line.startswith('X'):
                        x_str = line[1:]
                    elif line.startswith('Y'):
                        y_str = line[1:]

                    def parse_coord(coord_str: str) -> float:
                        """Parse coordinate string considering format and zero suppression."""
                        # If explicit decimal point present, parse directly
                        if '.' in coord_str:
                            try:
                                return float(coord_str)
                            except ValueError:
                                return 0.0

                        # Handle signs
                        sign = 1
                        if coord_str.startswith('+'):
                            coord_str = coord_str[1:]
                        elif coord_str.startswith('-'):
                            sign = -1
                            coord_str = coord_str[1:]

                        length = len(coord_str)

                        # LZ: leading zeros present, trailing zeros suppressed
                        if zero_mode == 'LZ':
                            integer_part = coord_str[:int_digits].rjust(int_digits, '0')
                            decimal_part = coord_str[int_digits:]
                            decimal_part = decimal_part.ljust(dec_digits, '0')
                        else:  # TZ: trailing zeros present, leading zeros suppressed
                            if length <= dec_digits:
                                # No integer part provided
                                integer_part = '0'
                                decimal_part = coord_str.rjust(dec_digits, '0')
                            else:
                                integer_part = coord_str[:-dec_digits]
                                decimal_part = coord_str[-dec_digits:]
                                integer_part = integer_part if integer_part else '0'

                        try:
                            value = int(integer_part) + int(decimal_part) / (10 ** dec_digits)
                            return sign * value
                        except ValueError:
                            return 0.0

                    # Update current position
                    if x_str:
                        current_x = parse_coord(x_str)
                        if not metric:
                            current_x *= 25.4
                    if y_str:
                        current_y = parse_coord(y_str)
                        if not metric:
                            current_y *= 25.4

                    diameter = tools[current_tool]
                    self.drill_holes.append((current_x, current_y, diameter))

            print(f"\nParsed {len(self.drill_holes)} drill holes from '{self.input_file}'")
            
            # Print summary by hole size
            hole_sizes = {}
            for x, y, dia in self.drill_holes:
                hole_sizes[dia] = hole_sizes.get(dia, 0) + 1
            
            print("\nHole size summary:")
            for dia in sorted(hole_sizes.keys()):
                count = hole_sizes[dia]
                print(f"  {dia:.4f} mm: {count} holes")

        except FileNotFoundError:
            print(f"Error: Could not find file '{self.input_file}'")
            sys.exit(1)
        except Exception as e:
            print(f"Error parsing drill file: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def generate_gcode_header(self) -> List[str]:
        """Generate G-code header with initialization commands."""
        gcode = [
            "(Generated by excellon_to_gcode.py)",
            f"(Input file: {self.input_file})",
            f"(Bit size: {self.bit_size} mm)",
            f"(Drill depth: {self.drill_depth} mm)",
            f"(Total holes: {len(self.drill_holes)})",
            "",
            "G21 (Metric units)",
            "G90 (Absolute positioning)",
            "G94 (Feed per minute mode)",
            f"M3 S{self.spindle_speed} (Start spindle clockwise)",
            "G4 P2.0 (Pause 2 seconds for spindle to reach speed)",
            "",
            f"G0 Z{self.safe_height:.3f} (Move to safe height)",
            ""
        ]
        return gcode

    def generate_gcode_footer(self) -> List[str]:
        """Generate G-code footer with shutdown commands."""
        gcode = [
            "",
            f"G0 Z{self.safe_height:.3f} (Return to safe height)",
            "M5 (Stop spindle)",
            "M2 (End program)",
            ""
        ]
        return gcode

    def generate_straight_drill(self, x: float, y: float) -> List[str]:
        """
        Generate G-code for a straight plunge drill operation.
        
        Args:
            x: X coordinate in mm
            y: Y coordinate in mm
            
        Returns:
            List of G-code commands
        """
        gcode = [
            f"G0 X{x:.4f} Y{y:.4f} (Position over hole)",
            f"G0 Z{self.clearance_height:.3f} (Move to clearance height)",
            f"G1 Z-{self.drill_depth:.3f} F{self.plunge_rate:.1f} (Drill down)",
            f"G0 Z{self.clearance_height:.3f} (Retract)",
            ""
        ]
        return gcode

    def generate_spiral_mill(self, x: float, y: float, hole_diameter: float) -> List[str]:
        """
        Generate G-code for spiral milling a hole.
        
        The bit spirals inward from the hole edge, accounting for bit radius.
        
        Args:
            x: X coordinate of hole center in mm
            y: Y coordinate of hole center in mm
            hole_diameter: Diameter of the hole to mill in mm
            
        Returns:
            List of G-code commands
        """
        gcode = [f"(Spiral mill hole: dia {hole_diameter:.4f} mm at X{x:.4f} Y{y:.4f})"]
        
        # Calculate the milling radius (subtract bit radius to cut inside the hole)
        hole_radius = hole_diameter / 2.0
        mill_radius = hole_radius - self.bit_radius
        
        if mill_radius <= 0:
            # Hole is too small or equal to bit size, use straight drill instead
            gcode.append("(Hole size <= bit size, using straight drill)")
            gcode.extend(self.generate_straight_drill(x, y))
            return gcode
        
        # Number of spiral passes (increase for deeper holes)
        # Use smaller Z increments for smoother operation
        z_step = 0.5  # mm per spiral pass
        num_passes = math.ceil(self.drill_depth / z_step)
        z_step = self.drill_depth / num_passes  # Recalculate for exact depth
        
        # Number of segments per circle (more segments = smoother circle)
        segments_per_circle = 36
        angle_step = 2 * math.pi / segments_per_circle
        
        # Start position: move to hole center
        gcode.append(f"G0 X{x:.4f} Y{y:.4f} (Move to hole center)")
        gcode.append(f"G0 Z{self.clearance_height:.3f} (Move to clearance height)")
        
        # Entry: move to starting radius at Z clearance
        start_x = x + mill_radius
        start_y = y
        gcode.append(f"G1 X{start_x:.4f} Y{start_y:.4f} F{self.feed_rate:.1f} (Move to starting radius)")
        
        # Spiral down while making circular passes
        current_z = 0.0
        
        for pass_num in range(num_passes):
            current_z -= z_step
            
            # Make one complete circle at this Z depth
            for seg in range(segments_per_circle + 1):  # +1 to close the circle
                angle = seg * angle_step
                seg_x = x + mill_radius * math.cos(angle)
                seg_y = y + mill_radius * math.sin(angle)
                
                # On first segment of each pass, include Z movement (spiral)
                if seg == 0:
                    gcode.append(f"G1 X{seg_x:.4f} Y{seg_y:.4f} Z{current_z:.4f} F{self.plunge_rate:.1f}")
                else:
                    gcode.append(f"G1 X{seg_x:.4f} Y{seg_y:.4f} F{self.feed_rate:.1f}")
        
        # Return to center and retract
        gcode.append(f"G1 X{x:.4f} Y{y:.4f} F{self.feed_rate:.1f} (Return to center)")
        gcode.append(f"G0 Z{self.clearance_height:.3f} (Retract)")
        gcode.append("")
        
        return gcode

    def generate_spiral_mill_arcs(self, x: float, y: float, hole_diameter: float) -> List[str]:
        """
        Generate G-code for spiral milling a hole using G2/G3 arc moves.
        
        This creates much more compact G-code compared to line segment approximation.
        Uses helical interpolation (G2/G3 with Z movement) for efficient spiral milling.
        
        Args:
            x: X coordinate of hole center in mm
            y: Y coordinate of hole center in mm
            hole_diameter: Diameter of the hole to mill in mm
            
        Returns:
            List of G-code commands
        """
        gcode = [f"(Spiral mill hole with arcs: dia {hole_diameter:.4f} mm at X{x:.4f} Y{y:.4f})"]
        
        # Calculate the milling radius (subtract bit radius to cut inside the hole)
        hole_radius = hole_diameter / 2.0
        mill_radius = hole_radius - self.bit_radius
        
        if mill_radius <= 0:
            # Hole is too small or equal to bit size, use straight drill instead
            gcode.append("(Hole size <= bit size, using straight drill)")
            gcode.extend(self.generate_straight_drill(x, y))
            return gcode
        
        # Number of spiral passes
        z_step = 0.5  # mm per spiral pass
        num_passes = math.ceil(self.drill_depth / z_step)
        z_step = self.drill_depth / num_passes  # Recalculate for exact depth
        
        # Start position: move to hole center
        gcode.append(f"G0 X{x:.4f} Y{y:.4f} (Move to hole center)")
        gcode.append(f"G0 Z{self.clearance_height:.3f} (Move to clearance height)")
        
        # Entry: move to starting radius at Z clearance
        start_x = x + mill_radius
        start_y = y
        gcode.append(f"G1 X{start_x:.4f} Y{start_y:.4f} F{self.feed_rate:.1f} (Move to starting radius)")
        
        # Spiral down using helical interpolation
        # G2 = clockwise arc, I and J are offsets from current position to arc center
        current_z = 0.0
        
        for pass_num in range(num_passes):
            current_z -= z_step
            
            # Calculate I and J offsets (from start position to center)
            i_offset = x - start_x  # Offset in X
            j_offset = y - start_y  # Offset in Y
            
            # G2: Clockwise full circle with Z movement (helical interpolation)
            # End position is same as start (full circle)
            # I,J specify the center offset from current position
            gcode.append(
                f"G2 X{start_x:.4f} Y{start_y:.4f} Z{current_z:.4f} "
                f"I{i_offset:.4f} J{j_offset:.4f} F{self.plunge_rate:.1f}"
            )
        
        # Return to center and retract
        gcode.append(f"G1 X{x:.4f} Y{y:.4f} F{self.feed_rate:.1f} (Return to center)")
        gcode.append(f"G0 Z{self.clearance_height:.3f} (Retract)")
        gcode.append("")
        
        return gcode

    def generate_gcode(self):
        """Generate complete G-code file from parsed drill holes."""
        if not self.drill_holes:
            print("Error: No drill holes found in file")
            sys.exit(1)

        try:
            with open(self.output_file, 'w') as f:
                # Write header
                for line in self.generate_gcode_header():
                    f.write(line + '\n')

                # Process each hole
                print(f"\nGenerating G-code for {len(self.drill_holes)} holes...")
                
                drill_count = 0
                mill_count = 0
                
                for x, y, hole_diameter in self.drill_holes:
                    if hole_diameter <= self.bit_size:
                        # Straight drill for holes equal to or smaller than bit
                        gcode = self.generate_straight_drill(x, y)
                        drill_count += 1
                    else:
                        # Spiral mill for larger holes
                        if self.use_arcs:
                            gcode = self.generate_spiral_mill_arcs(x, y, hole_diameter)
                        else:
                            gcode = self.generate_spiral_mill(x, y, hole_diameter)
                        mill_count += 1
                    
                    for line in gcode:
                        f.write(line + '\n')

                # Write footer
                for line in self.generate_gcode_footer():
                    f.write(line + '\n')

            print(f"\nG-code generation complete!")
            print(f"  Straight drilled: {drill_count} holes")
            print(f"  Spiral milled: {mill_count} holes")
            print(f"  Output file: {self.output_file}")

        except Exception as e:
            print(f"Error writing G-code file: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def convert(self):
        """Main conversion process."""
        print("Excellon to G-code Converter")
        print("=" * 50)
        self.parse_excellon_file()
        self.generate_gcode()
        print("\nConversion successful!")


def main():
    parser = argparse.ArgumentParser(
        description="Convert Excellon drill files to G-code for CNC milling.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.drl
  %(prog)s input.drl -o output.nc
  %(prog)s input.drl --bit-size 1.5 --depth 2.5
  %(prog)s input.drl -b 0.8 -d 1.6 -f 150 -p 75
        """
    )
    
    parser.add_argument(
        "input_file",
        help="Path to the Excellon drill file (.drl, .xln, .txt)"
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Output G-code file path (default: input_file.nc)",
        default=None
    )
    
    parser.add_argument(
        "-b", "--bit-size",
        type=float,
        default=1.0,
        help="Milling bit diameter in mm (default: 1.0)"
    )
    
    parser.add_argument(
        "-d", "--depth",
        type=float,
        default=2.0,
        help="Drill/mill depth in mm (default: 2.0)"
    )
    
    parser.add_argument(
        "-f", "--feed-rate",
        type=float,
        default=100.0,
        help="XY feed rate in mm/min (default: 100.0)"
    )
    
    parser.add_argument(
        "-p", "--plunge-rate",
        type=float,
        default=50.0,
        help="Z plunge rate in mm/min (default: 50.0)"
    )
    
    parser.add_argument(
        "-s", "--spindle-speed",
        type=int,
        default=10000,
        help="Spindle speed in RPM (default: 10000)"
    )
    
    parser.add_argument(
        "--safe-height",
        type=float,
        default=5.0,
        help="Safe Z height for rapid moves in mm (default: 5.0)"
    )
    
    parser.add_argument(
        "--clearance-height",
        type=float,
        default=2.0,
        help="Z clearance height above workpiece in mm (default: 2.0)"
    )
    
    parser.add_argument(
        "--use-arcs",
        action="store_true",
        help="Use G2/G3 arc moves for spiral milling (more compact output)"
    )

    args = parser.parse_args()

    # Auto-generate output filename if not specified
    if args.output is None:
        output_file = args.input_file + '.nc'
    else:
        output_file = args.output

    # Validate parameters
    if args.bit_size <= 0:
        print("Error: Bit size must be positive")
        sys.exit(1)
    if args.depth <= 0:
        print("Error: Drill depth must be positive")
        sys.exit(1)

    # Create converter and run
    converter = ExcellonToGcode(
        input_file=args.input_file,
        output_file=output_file,
        bit_size=args.bit_size,
        drill_depth=args.depth,
        feed_rate=args.feed_rate,
        plunge_rate=args.plunge_rate,
        spindle_speed=args.spindle_speed,
        safe_height=args.safe_height,
        clearance_height=args.clearance_height,
        use_arcs=args.use_arcs
    )
    
    converter.convert()


if __name__ == "__main__":
    main()
