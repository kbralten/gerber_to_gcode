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
from typing import List, Tuple, Dict, Optional

# Optional imports for outline routing
try:
    from pygerber.gerberx3.tokenizer.tokenizer import Tokenizer
    from pygerber.gerberx3.parser2.parser2 import Parser2
    from pygerber.gerberx3.parser2.commands2.line2 import Line2
    from pygerber.gerberx3.parser2.commands2.arc2 import Arc2
    from pygerber.gerberx3.parser2.commands2.region2 import Region2
    from shapely.geometry import LineString, Polygon, MultiPolygon
    from shapely.ops import unary_union
    GERBER_SUPPORT = True
except ImportError:
    GERBER_SUPPORT = False


class ExcellonToGcode:
    """Convert Excellon drill files to G-code for CNC milling."""

    def __init__(self, input_file: str, output_file: str, bit_size: float, 
                 drill_depth: float, feed_rate: float = 100.0, 
                 plunge_rate: float = 50.0, spindle_speed: int = 10000,
                 safe_height: float = 5.0, clearance_height: float = 2.0,
                 use_arcs: bool = False, outline_file: Optional[str] = None,
                 reset_origin_lower_left: bool = False):
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
            outline_file: Optional path to Gerber outline file for board routing
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
        self.outline_file = outline_file
        self.reset_origin_lower_left = reset_origin_lower_left
        self.drill_holes: List[Tuple[float, float, float]] = []
        self.slots: List[Tuple[float, float, float, float, float]] = []  # start_x, start_y, end_x, end_y, diameter
        self.outline_paths: List[List[Tuple[float, float]]] = []  # List of paths (outer and inner)

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

            last_rapid = None
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

                # Also handle G-code style move pairs for slots (KiCad style in some drill exports)
                # Example sequence in file:
                # G00X128.0Y-94.0
                # M15
                # G01X128.0Y-91.0
                # M16
                # Match rapid move G00 but avoid matching G01 (which also starts with 'G0')
                if line.startswith('G00') or (line.startswith('G0') and not line.startswith('G01')):
                    # Rapid move to potential slot start
                    mx = re.search(r'X([+-]?\d*\.?\d+)', line)
                    my = re.search(r'Y([+-]?\d*\.?\d+)', line)
                    if mx or my:
                        try:
                            rx = float(mx.group(1)) if mx else current_x
                            ry = float(my.group(1)) if my else current_y
                            # convert units if necessary
                            if not metric:
                                rx *= 25.4
                                ry *= 25.4
                            sd = tools.get(current_tool) if current_tool else None
                            last_rapid = (rx, ry, current_tool, sd)
                        except Exception:
                            last_rapid = None
                    else:
                        last_rapid = None

                elif line.startswith('G01') or (line.startswith('G1') and not line.startswith('G10')):
                    # Linear move - if it's paired with a previous rapid (and wrapped by M15/M16), record as slot
                    mx = re.search(r'X([+-]?\d*\.?\d+)', line)
                    my = re.search(r'Y([+-]?\d*\.?\d+)', line)
                    if mx or my:
                        try:
                            lx = float(mx.group(1)) if mx else current_x
                            ly = float(my.group(1)) if my else current_y
                            if not metric:
                                lx *= 25.4
                                ly *= 25.4
                            # If we have a recorded rapid start, add a slot
                            if last_rapid:
                                sx, sy, _, sd = last_rapid
                                if sd is None:
                                    sd = tools.get(current_tool)
                                self.slots.append((sx, sy, lx, ly, sd))
                                last_rapid = None
                        except Exception:
                            pass

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

    def parse_outline_file(self):
        """Parse Gerber outline file and extract path contours."""
        if not self.outline_file:
            return
        
        if not GERBER_SUPPORT:
            print("Warning: pygerber and shapely are required for outline routing")
            print("Install with: pip install pygerber shapely")
            return
        
        try:
            print(f"\nParsing outline file '{self.outline_file}'...")
            
            with open(self.outline_file, 'r') as f:
                source_code = f.read()
            
            # Tokenize and parse Gerber file
            tokenizer = Tokenizer()
            tokens = tokenizer.tokenize(source_code)
            parser = Parser2()
            command_buffer = parser.parse(tokens)
            
            # Extract paths from commands - build continuous paths
            current_path = []
            last_point = None
            
            for command in command_buffer.commands:
                if isinstance(command, Line2):
                    # Extract line coordinates
                    x1 = command.start_point.x.as_millimeters()
                    y1 = command.start_point.y.as_millimeters()
                    x2 = command.end_point.x.as_millimeters()
                    y2 = command.end_point.y.as_millimeters()
                    
                    # Check if this line connects to the previous path
                    if last_point and (abs(last_point[0] - x1) > 0.001 or abs(last_point[1] - y1) > 0.001):
                        # Discontinuity detected - save current path and start new one
                        if current_path and len(current_path) >= 3:
                            self.outline_paths.append(current_path)
                        current_path = []
                    
                    # Add to current path
                    if not current_path:
                        current_path.append((x1, y1))
                    current_path.append((x2, y2))
                    last_point = (x2, y2)
                    
                elif isinstance(command, Arc2):
                    # Approximate arc with line segments and add to current path
                    x1 = command.start_point.x.as_millimeters()
                    y1 = command.start_point.y.as_millimeters()
                    x2 = command.end_point.x.as_millimeters()
                    y2 = command.end_point.y.as_millimeters()
                    cx = command.center_point.x.as_millimeters()
                    cy = command.center_point.y.as_millimeters()
                    
                    # Check for discontinuity
                    if last_point and (abs(last_point[0] - x1) > 0.001 or abs(last_point[1] - y1) > 0.001):
                        if current_path and len(current_path) >= 3:
                            self.outline_paths.append(current_path)
                        current_path = []
                    
                    if not current_path:
                        current_path.append((x1, y1))
                    
                    # Calculate arc parameters
                    radius = math.sqrt((x1 - cx)**2 + (y1 - cy)**2)
                    start_angle = math.atan2(y1 - cy, x1 - cx)
                    end_angle = math.atan2(y2 - cy, x2 - cx)
                    
                    # Determine arc direction
                    is_clockwise = getattr(command, 'is_clockwise', False)
                    if is_clockwise:
                        if end_angle > start_angle:
                            end_angle -= 2 * math.pi
                    else:
                        if end_angle < start_angle:
                            end_angle += 2 * math.pi
                    
                    # Generate arc points (skip first point as it's already in path)
                    num_segments = max(8, int(abs(end_angle - start_angle) * radius * 2))
                    for i in range(1, num_segments + 1):
                        t = i / num_segments
                        angle = start_angle + t * (end_angle - start_angle)
                        px = cx + radius * math.cos(angle)
                        py = cy + radius * math.sin(angle)
                        current_path.append((px, py))
                    last_point = (x2, y2)
                    
                elif isinstance(command, Region2):
                    # Regions are separate contours, save current path and start new one
                    if current_path and len(current_path) >= 3:
                        self.outline_paths.append(current_path)
                        current_path = []
                    
                    # Process region as a closed path
                    region_points = []
                    for segment in command.command_buffer.commands:
                        if isinstance(segment, Line2):
                            if not region_points:
                                region_points.append((
                                    segment.start_point.x.as_millimeters(),
                                    segment.start_point.y.as_millimeters()
                                ))
                            region_points.append((
                                segment.end_point.x.as_millimeters(),
                                segment.end_point.y.as_millimeters()
                            ))
                        elif isinstance(segment, Arc2):
                            # Handle arcs in regions (simplified)
                            if not region_points:
                                region_points.append((
                                    segment.start_point.x.as_millimeters(),
                                    segment.start_point.y.as_millimeters()
                                ))
                            region_points.append((
                                segment.end_point.x.as_millimeters(),
                                segment.end_point.y.as_millimeters()
                            ))
                    
                    if region_points and len(region_points) >= 3:
                        self.outline_paths.append(region_points)
            
            # Add any remaining path
            if current_path and len(current_path) >= 3:
                self.outline_paths.append(current_path)
            
            print(f"Parsed {len(self.outline_paths)} outline contour(s)")
            
        except FileNotFoundError:
            print(f"Warning: Could not find outline file '{self.outline_file}'")
        except Exception as e:
            print(f"Warning: Failed to parse outline file: {e}")
            import traceback
            traceback.print_exc()

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
        
        # Decide whether to return to center. If returning to center would
        # require cutting across material (hole large compared to bit), skip
        # the move and retract from the current tool position instead.
        if hole_diameter <= 2 * self.bit_size:
            gcode.append(f"G1 X{x:.4f} Y{y:.4f} F{self.feed_rate:.1f} (Return to center)")
        else:
            gcode.append("(Skipping return to center to avoid cutting; retracting from current position)")
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
        
        # Decide whether to return to center. If returning to center would
        # require cutting across material (hole large compared to bit), skip
        # the move and retract from the current tool position instead.
        if hole_diameter <= 2 * self.bit_size:
            gcode.append(f"G1 X{x:.4f} Y{y:.4f} F{self.feed_rate:.1f} (Return to center)")
        else:
            gcode.append("(Skipping return to center to avoid cutting; retracting from current position)")
        gcode.append(f"G0 Z{self.clearance_height:.3f} (Retract)")
        gcode.append("")
        
        return gcode

    def generate_outline_routing(self, path: List[Tuple[float, float]], is_outer: bool = True) -> List[str]:
        """
        Generate G-code for routing an outline path with tool offset.
        
        Args:
            path: List of (x, y) coordinates defining the path
            is_outer: True for outer contour (offset outward), False for inner (offset inward)
            
        Returns:
            List of G-code commands
        """
        if not GERBER_SUPPORT or len(path) < 3:
            return []
        
        gcode = [f"(Routing outline path: {len(path)} points, {'outer' if is_outer else 'inner'} contour)"]
        
        try:
            # Create a polygon from the path
            poly = Polygon(path)
            
            # Offset the polygon by tool radius
            # Positive offset for outer contour (cut outside), negative for inner (cut inside)
            offset_distance = self.bit_radius if is_outer else -self.bit_radius
            offset_poly = poly.buffer(offset_distance, join_style=2)  # join_style=2 is mitre
            
            # Extract offset coordinates
            if offset_poly.is_empty:
                gcode.append("(Warning: Offset path is empty, skipping)")
                return gcode
            
            # Get the exterior coordinates
            if hasattr(offset_poly, 'exterior'):
                offset_coords = list(offset_poly.exterior.coords)
            else:
                offset_coords = list(offset_poly.coords)
            
            if len(offset_coords) < 3:
                gcode.append("(Warning: Offset path too short, skipping)")
                return gcode
            
            # Calculate number of Z passes
            z_step = 0.5  # mm per pass
            num_passes = math.ceil(self.drill_depth / z_step)
            z_step = self.drill_depth / num_passes
            
            # Move to start position
            start_x, start_y = offset_coords[0]
            gcode.append(f"G0 X{start_x:.4f} Y{start_y:.4f} (Move to path start)")
            gcode.append(f"G0 Z{self.clearance_height:.3f} (Move to clearance height)")
            
            # Multiple Z passes
            current_z = 0.0
            for pass_num in range(num_passes):
                current_z -= z_step
                
                # Plunge to depth
                gcode.append(f"G1 Z{current_z:.4f} F{self.plunge_rate:.1f} (Pass {pass_num + 1}/{num_passes})")
                
                # Route the path
                for i in range(1, len(offset_coords)):
                    px, py = offset_coords[i]
                    gcode.append(f"G1 X{px:.4f} Y{py:.4f} F{self.feed_rate:.1f}")
                
                # Return to start to close the loop
                gcode.append(f"G1 X{start_x:.4f} Y{start_y:.4f} F{self.feed_rate:.1f} (Close path)")
            
            # Retract
            gcode.append(f"G0 Z{self.clearance_height:.3f} (Retract)")
            gcode.append("")
            
        except Exception as e:
            gcode.append(f"(Error generating offset path: {e})")
            print(f"Warning: Error offsetting path: {e}")
        
        return gcode

    def generate_slot_routing(self, sx: float, sy: float, ex: float, ey: float, diameter: float) -> List[str]:
        """
        Generate G-code for routing a linear slot between two points using centerline multi-pass routing.

        Args:
            sx, sy: Start coordinate in mm
            ex, ey: End coordinate in mm
            diameter: Tool diameter used for the slot

        Returns:
            List of G-code commands
        """
        gcode: List[str] = [f"(Slot route: start=({sx:.3f},{sy:.3f}) end=({ex:.3f},{ey:.3f}) dia={diameter:.3f})"]

        # Compute slot length and direction
        dx = ex - sx
        dy = ey - sy
        length = math.hypot(dx, dy)
        if length < 0.001:
            gcode.append('(Warning: zero-length slot, skipping)')
            return gcode

        # Number of Z passes
        z_step = 0.5
        num_passes = math.ceil(self.drill_depth / z_step)
        z_step = self.drill_depth / num_passes

        # Unit vector along slot
        ux = dx / length
        uy = dy / length

        # Starting and ending points are centerline of slot
        start_x, start_y = sx, sy
        end_x, end_y = ex, ey

        # Slot width provided by Excellon entry
        slot_width = diameter

        # If we have shapely available and the slot is wider than the bit,
        # construct the slot polygon and route the interior contour (slot minus bit radius).
        if GERBER_SUPPORT and slot_width > self.bit_size + 1e-6:
            try:
                # Build slot polygon (centerline buffered by half slot width)
                slot_line = LineString([(start_x, start_y), (end_x, end_y)])
                slot_poly = slot_line.buffer(slot_width / 2.0, cap_style=1, join_style=1)

                # Offset inward by bit radius to get tool center path(s)
                inner_poly = slot_poly.buffer(-self.bit_radius, join_style=1)

                if inner_poly.is_empty:
                    # Fallback to centerline passes
                    raise RuntimeError('Inner offset empty')

                # Handle MultiPolygon or Polygon
                polygons = []
                if isinstance(inner_poly, MultiPolygon):
                    polygons = list(inner_poly)
                else:
                    polygons = [inner_poly]

                for poly in polygons:
                    coords = list(poly.exterior.coords)
                    if len(coords) < 3:
                        continue

                    # Route this contour with multiple Z passes
                    gcode.append(f"(Routing interior contour with {len(coords)} points)")
                    start_px, start_py = coords[0]
                    gcode.append(f"G0 X{start_px:.4f} Y{start_py:.4f} (Move to contour start)")
                    gcode.append(f"G0 Z{self.clearance_height:.3f} (Move to clearance height)")

                    current_z = 0.0
                    for p in range(num_passes):
                        current_z -= z_step
                        gcode.append(f"G1 Z{current_z:.4f} F{self.plunge_rate:.1f} (Pass {p+1}/{num_passes})")
                        for i in range(1, len(coords)):
                            px, py = coords[i]
                            gcode.append(f"G1 X{px:.4f} Y{py:.4f} F{self.feed_rate:.1f}")
                        # Close loop back to start
                        gcode.append(f"G1 X{start_px:.4f} Y{start_py:.4f} F{self.feed_rate:.1f} (Close contour)")
                        gcode.append(f"G0 Z{self.clearance_height:.3f}")

                # Final retract
                gcode.append(f"G0 Z{self.clearance_height:.3f} (Retract)")
                gcode.append("")
                return gcode
            except Exception:
                # If anything goes wrong with shapely, fall back to centerline routing
                gcode.append('(Warning: interior contour routing failed, falling back to centerline)')

        # Default/fallback: simple centerline multi-pass routing
        gcode.append(f"G0 X{start_x:.4f} Y{start_y:.4f} (Move to slot start)")
        gcode.append(f"G0 Z{self.clearance_height:.3f} (Move to clearance height)")

        current_z = 0.0
        for p in range(num_passes):
            current_z -= z_step
            gcode.append(f"G1 Z{current_z:.4f} F{self.plunge_rate:.1f} (Pass {p+1}/{num_passes})")
            gcode.append(f"G1 X{end_x:.4f} Y{end_y:.4f} F{self.feed_rate:.1f}")
            gcode.append(f"G0 Z{self.clearance_height:.3f}")
            if p < num_passes - 1:
                gcode.append(f"G0 X{start_x:.4f} Y{start_y:.4f}")

        gcode.append(f"G0 Z{self.clearance_height:.3f} (Retract)")
        gcode.append("")
        return gcode

    def generate_gcode(self):
        """Generate complete G-code file from parsed drill holes and outline paths."""
        if not self.drill_holes and not self.outline_paths and not self.slots:
            print("Error: No drill holes or outline paths found")
            sys.exit(1)
        try:
            # Buffer all generated lines first so we can optionally shift origin
            all_lines: List[str] = []

            # Header
            all_lines.extend(self.generate_gcode_header())

            # Process drill holes
            if self.drill_holes:
                print(f"\nGenerating G-code for {len(self.drill_holes)} holes...")
                drill_count = 0
                mill_count = 0

                for x, y, hole_diameter in self.drill_holes:
                    if hole_diameter <= self.bit_size:
                        gcode = self.generate_straight_drill(x, y)
                        drill_count += 1
                    else:
                        if self.use_arcs:
                            gcode = self.generate_spiral_mill_arcs(x, y, hole_diameter)
                        else:
                            gcode = self.generate_spiral_mill(x, y, hole_diameter)
                        mill_count += 1
                    all_lines.extend(gcode)

                print(f"  Straight drilled: {drill_count} holes")
                print(f"  Spiral milled: {mill_count} holes")

            # Process outline paths
            if self.outline_paths:
                print(f"\nGenerating G-code for {len(self.outline_paths)} outline path(s)...")

                for i, path in enumerate(self.outline_paths):
                    if GERBER_SUPPORT and len(path) >= 3:
                        poly = Polygon(path)
                        is_outer = (poly.area == max(Polygon(p).area for p in self.outline_paths if len(p) >= 3))
                        gcode = self.generate_outline_routing(path, is_outer)
                        all_lines.extend(gcode)

                print(f"  Routed {len(self.outline_paths)} outline contour(s)")

            # Process detected slots (from Excellon/G-code style drill files)
            if self.slots:
                print(f"\nGenerating G-code for {len(self.slots)} slot(s)...")
                for sx, sy, ex, ey, dia in self.slots:
                    gcode = self.generate_slot_routing(sx, sy, ex, ey, dia)
                    all_lines.extend(gcode)
                print(f"  Routed {len(self.slots)} slot(s)")

            # Footer
            all_lines.extend(self.generate_gcode_footer())

            # If requested, compute lower-left bounding box and shift X/Y coordinates
            if self.reset_origin_lower_left:
                # Find all X/Y coordinates in G-code (ignore comments in parentheses)
                xs = []
                ys = []
                coord_re_x = re.compile(r'X([+-]?\d*\.?\d+)')
                coord_re_y = re.compile(r'Y([+-]?\d*\.?\d+)')

                for ln in all_lines:
                    code_part = ln.split('(', 1)[0]  # drop comments in parentheses
                    mx = coord_re_x.search(code_part)
                    my = coord_re_y.search(code_part)
                    if mx:
                        try:
                            xs.append(float(mx.group(1)))
                        except ValueError:
                            pass
                    if my:
                        try:
                            ys.append(float(my.group(1)))
                        except ValueError:
                            pass

                if xs and ys:
                    min_x = min(xs)
                    min_y = min(ys)
                    dx = min_x
                    dy = min_y

                    def shift_line(line: str) -> str:
                        # Keep comments intact
                        parts = line.split('(', 1)
                        code = parts[0]
                        comment = '(' + parts[1] if len(parts) > 1 else ''

                        # Replace X and Y occurrences with shifted values
                        def repl_x(m):
                            try:
                                val = float(m.group(1)) - dx
                                return f'X{val:.4f}'
                            except Exception:
                                return m.group(0)

                        def repl_y(m):
                            try:
                                val = float(m.group(1)) - dy
                                return f'Y{val:.4f}'
                            except Exception:
                                return m.group(0)

                        code = coord_re_x.sub(repl_x, code)
                        code = coord_re_y.sub(repl_y, code)
                        return code + comment

                    all_lines = [shift_line(ln) for ln in all_lines]

            # Write out file
            with open(self.output_file, 'w') as f:
                for line in all_lines:
                    f.write(line + '\n')

            print(f"\nG-code generation complete!")
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
        self.parse_outline_file()
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
    
    parser.add_argument(
        "--outline",
        type=str,
        default=None,
        help="Optional Gerber outline file for board routing (.gbr)"
    )

    parser.add_argument(
        "--origin-lower-left",
        action="store_true",
        help="Reset origin to lower-left of bounding box around all movements (shift all X/Y so lower-left becomes 0,0)"
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
        use_arcs=args.use_arcs,
        outline_file=args.outline,
        reset_origin_lower_left=args.origin_lower_left
    )
    
    converter.convert()


if __name__ == "__main__":
    main()
