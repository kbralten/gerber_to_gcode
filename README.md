# Excellon to G-code Converter

Convert Excellon drill files to G-code for CNC milling machines. This tool intelligently handles different hole sizes by using straight plunge drilling for small holes and spiral milling for larger holes.

## Features

- **Excellon Format Support**: Parses standard Excellon drill files with tool definitions, coordinates, and various format options
- **Gerber Outline Routing**: Routes PCB outlines from Gerber files with automatic tool offset compensation
- **Smart Drilling Strategy**: 
  - Straight plunge for holes ≤ bit size
  - Spiral milling for holes > bit size (accounts for bit radius)
- **Arc Move Support**: Optional G2/G3 helical interpolation for compact G-code (85% smaller files!)
- **Intelligent Offset**: Automatically offsets tool to outside of outer contours and inside of inner slots
- **Metric and Imperial Units**: Automatically handles both METRIC and INCH files
- **Zero Suppression**: Supports both LZ (leading zeros) and TZ (trailing zeros) formats
- **Configurable Parameters**: Bit size, depth, feed rates, spindle speed, and more
- **Safe G-code**: Includes proper initialization, safe heights, and spindle control

## Installation

**Dependencies:**
- Python 3.6+
- For outline routing: `pygerber>=2.0.0` and `shapely>=2.0.0`

```bash
# Clone or download the repository
git clone <repository-url>
cd gerber_to_gcode

# Install optional dependencies for outline routing
pip install -r requirements.txt

# Make the script executable (optional, Linux/Mac)
chmod +x excellon_to_gcode.py
```

## Usage

### Basic Usage

```bash
python excellon_to_gcode.py input.drl
```

This will create `input.drl.nc` with default parameters:
- Bit size: 1.0 mm
- Drill depth: 2.0 mm
- Feed rate: 100 mm/min
- Plunge rate: 50 mm/min
- Spindle speed: 10000 RPM

### Specify Output File

```bash
python excellon_to_gcode.py input.drl -o output.nc
```

### Custom Bit Size and Depth

```bash
python excellon_to_gcode.py input.drl --bit-size 1.5 --depth 2.5
```

Or using short options:
```bash
python excellon_to_gcode.py input.drl -b 1.5 -d 2.5
```

### Use Arc Moves for Compact Output

Generate much smaller G-code files using G2/G3 helical interpolation:

```bash
python excellon_to_gcode.py input.drl --use-arcs
```

This creates **85% smaller files** by using arc moves instead of line segments for spiral milling!

### Route PCB Outline

Add board outline routing from a Gerber file:

```bash
python excellon_to_gcode.py input.drl --outline board_outline.gbr
```

The tool automatically:
- Offsets the tool to the **outside** of the outermost contour
- Offsets the tool to the **inside** of inner contours (slots/cutouts)
- Routes in multiple passes based on the depth setting

Combine with drilling and arc moves:

```bash
python excellon_to_gcode.py input.drl \
  --outline board_outline.gbr \
  --use-arcs \
  --bit-size 1.0 \
  --depth 1.6
```

### Full Custom Parameters

```bash
python excellon_to_gcode.py input.drl \
  --bit-size 0.8 \
  --depth 1.6 \
  --feed-rate 150 \
  --plunge-rate 75 \
  --spindle-speed 12000 \
  --safe-height 10.0 \
  --clearance-height 3.0
```

## Command Line Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `input_file` | - | str | required | Path to Excellon drill file |
| `--output` | `-o` | str | input.nc | Output G-code file path |
| `--outline` | - | str | none | Gerber outline file for routing |
| `--bit-size` | `-b` | float | 1.0 | Milling bit diameter in mm |
| `--depth` | `-d` | float | 2.0 | Drill/mill depth in mm |
| `--feed-rate` | `-f` | float | 100.0 | XY feed rate in mm/min |
| `--plunge-rate` | `-p` | float | 50.0 | Z plunge rate in mm/min |
| `--spindle-speed` | `-s` | int | 10000 | Spindle speed in RPM |
| `--safe-height` | - | float | 5.0 | Safe Z height for rapid moves in mm |
| `--clearance-height` | - | float | 2.0 | Z clearance above workpiece in mm |
| `--use-arcs` | - | flag | false | Use G2/G3 arc moves (compact output) |
| `--origin-lower-left` | - | flag | false | Shift all X/Y so lower-left of bounding box becomes (0,0) |

## How It Works

### Excellon File Parsing

The program parses Excellon drill files following the standard format:

1. **Header Information**: Extracts format (integer:decimal digits), unit mode (METRIC/INCH), and zero suppression mode (LZ/TZ)
2. **Tool Definitions**: Reads tool numbers and their diameters (e.g., `T01C0.3000`)
3. **Tool Selection**: Tracks which tool is currently selected (e.g., `T01`)
4. **Coordinates**: Parses X/Y coordinates with proper handling of format and zero suppression

### Drilling vs. Milling Strategy

**Straight Plunge Drilling** (hole diameter ≤ bit size):
```
1. Rapid move to XY position
2. Rapid move to clearance height
3. Plunge down to drill depth
4. Rapid retract
```

**Spiral Milling** (hole diameter > bit size):
```
1. Rapid move to hole center
2. Move to starting radius (hole_radius - bit_radius)
3. Spiral down in passes while making circular movements
4. Multiple passes for smooth cutting
5. Return to center and retract
```

The spiral milling accounts for the bit radius to ensure the final hole matches the specified diameter.

**Two Spiral Milling Modes:**

- **Linear segments** (default): Uses G1 moves to approximate circles with 36 segments per revolution
- **Arc moves** (`--use-arcs`): Uses G2/G3 helical interpolation for true circular arcs

**File Size Comparison** (example with 5 spiral-milled holes):
- Linear segments: ~24 KB (37 G1 commands per circle pass)
- Arc moves: ~3.7 KB (1 G2 command per circle pass) - **85% smaller!**

### Slot Handling

- **Detection**: The converter recognizes linear slots exported as paired rapid+linear moves (common in KiCad/Excellon drill exports) and records them as start/end centerlines.
- **Interior Contour Routing**: For slots wider than the selected bit, the tool constructs a slot polygon from the centerline, offsets it inward by the bit radius, and routes the resulting interior contour(s) so the finished slot matches the requested width.
- **Centerline Fallback**: For slots equal to or narrower than the bit (or when `shapely` is unavailable), the tool performs centerline multi-pass cutting along the slot centerline.
- **Safety**: If interior offset yields an empty path (too small), the converter falls back to safe centerline passes.

### G-code Output

Generated G-code includes:

- **Header**: Units, positioning mode, spindle startup
- **Safe Movements**: All rapids at safe height
- **Tool Operations**: Drilling or milling for each hole
- **Footer**: Spindle stop, program end

Example output structure:
```gcode
G21 (Metric units)
G90 (Absolute positioning)
M3 S10000 (Start spindle)
G0 Z5.000 (Safe height)

G0 X10.0000 Y20.0000
G0 Z2.000
G1 Z-2.000 F50.0
G0 Z2.000

M5 (Stop spindle)
M2 (End program)
```

### Outline Routing

When a Gerber outline file is provided with `--outline`, the tool:

1. **Parses Gerber commands**: Extracts Line2, Arc2, and Region2 commands from the Gerber X3 file
2. **Builds contours**: Detects discontinuities to separate outer board outline from inner slots/cutouts
3. **Determines contour type**: Uses shapely to compute polygon area and orientation
   - Largest contour = outer board outline → offset **outward** by tool radius
   - Smaller contours = inner slots/cutouts → offset **inward** by tool radius
4. **Multi-pass routing**: Routes each contour in multiple passes (0.5mm per pass) to reach full depth

**Offset logic example:**
- Board outline: 100mm × 80mm rectangle
- Tool: 1.0mm diameter (0.5mm radius)
- Outer path: (-0.5, -0.5) to (100.5, 80.5) - cuts **outside** the board
- Inner slot: (20, 20) to (80, 60)
- Inner path: (20.5, 20.5) to (79.5, 59.5) - cuts **inside** the slot

This ensures the board is cut to the correct size and slots have the correct dimensions.

## Excellon File Format Support

The parser supports:

- **Format Specifications**: `;FILE_FORMAT=4:4` (4 integer, 4 decimal digits)
- **Units**: `METRIC` (mm) and `INCH` (converted to mm)
- **Zero Suppression**: 
  - `LZ` (Leading Zeros): Leading zeros present, trailing suppressed
  - `TZ` (Trailing Zeros): Trailing zeros present, leading suppressed
- **Tool Definitions**: `T01C0.3000`, `T01F00S00C0.3000`, etc.
- **Coordinates**: `X123456Y789012`, `X123456`, `Y789012`
- **Decimal Points**: Explicit decimals (e.g., `X12.3456Y78.9012`)

## Example Excellon File

```
;FILE_FORMAT=4:4
METRIC,LZ
T01C0.8000
T02C1.0000
T03C3.0000
%
T01
X12500Y15000
X25000Y15000
T02
X12500Y25000
X25000Y25000
T03
X18750Y20000
M30
```

This file defines three tools (0.8mm, 1.0mm, 3.0mm) and drills 5 holes at specified positions.

## Tips and Best Practices

1. **Bit Selection**: Choose a bit size that works for most of your holes. Smaller holes can be drilled directly, larger holes will be milled.

2. **Depth Setting**: PCBs are typically 1.6mm thick. A depth of 2.0mm ensures complete drilling with some margin.

3. **Feed Rates**: Start conservative and increase based on your machine's capabilities:
   - Soft materials (FR4): 100-200 mm/min
   - Hard materials: 50-100 mm/min

4. **Spindle Speed**: Higher speeds (10000-20000 RPM) work well for small bits and PCB materials.

5. **Multiple Passes**: The spiral milling uses 0.5mm Z steps by default. Adjust in the code if needed for your material.

6. **Origin Reset**: If your PCB CAD places the board far from the sheet origin (KiCad "sheet coordinates"), use `--origin-lower-left` to translate all XY coordinates so the lower-left of the combined toolpath bounding box becomes `(0,0)`. This is useful to keep the machine origin near the workpiece and reduce long rapid travels.

## Troubleshooting

### "No drill holes found"
- Check that your file has tool definitions with `C` parameter (diameter)
- Verify coordinates are present after tool selection
- Ensure file format is standard Excellon

### Holes are wrong size
- Verify the Excellon file has correct tool diameters
- Check units (METRIC vs INCH) in the file
- Ensure bit size parameter matches your actual bit

### G-code won't run
- Verify your CNC controller supports G-code dialect used
- Check that spindle commands (M3/M5) are compatible
- Adjust feed rates if they're too fast for your machine

## Technical Details

### Coordinate Parsing

The parser handles zero-suppressed coordinates correctly:

**Leading Zero (LZ) Example**: Format 4:4, coordinate `12345678`
- Integer part: `1234` → 1234
- Decimal part: `5678` → 0.5678
- Result: 1234.5678 mm

**Trailing Zero (TZ) Example**: Format 4:4, coordinate `123456`
- Last 4 digits are decimal: `3456` → 0.3456
- Remaining digits are integer: `12` → 12
- Result: 12.3456 mm

### Spiral Milling Algorithm

The spiral milling creates smooth circular paths:

1. Calculate milling radius: `hole_radius - bit_radius`
2. Divide depth into 0.5mm passes
3. For each pass:
   - Generate 36 segments around circle
   - First segment includes Z movement (spiral)
   - Remaining segments are XY moves
4. Close each circle precisely

## License

AGPLv3 - contributions welcome

## Contributing

Contributions welcome! Please test with various Excellon files and report any parsing issues.

## References

- [Excellon Format Specification](http://web.archive.org/web/20071030075236/http://www.excellon.com/manuals/program.htm)
- [RS-274 G-code Standard](https://www.nist.gov/publications/nist-rs274ngc-interpreter-version-3)
