# Quick Start Guide

## Installation

1. Ensure you have Python 3.6 or higher installed:
   ```bash
   python --version
   ```

2. Clone or download this repository

3. No additional packages needed - uses Python standard library only!

## First Run

Try the included example file:

```bash
python excellon_to_gcode.py example.drl
```

This will create `example.drl.nc` with default settings.

## Your First Conversion

1. **Get your Excellon drill file** (usually `.drl`, `.xln`, or `.txt` extension from your PCB design software)

2. **Run the converter**:
   ```bash
   python excellon_to_gcode.py your_board.drl
   ```

3. **Check the output**:
   - Opens `your_board.drl.nc` in a text editor
   - Verify hole positions and operations
   - Check feed rates and depths are appropriate

4. **Adjust parameters if needed**:
   ```bash
   python excellon_to_gcode.py your_board.drl -b 1.5 -d 2.5 -f 150
   ```

## Common Scenarios

### Standard PCB (1.6mm thick, 1mm bit)
```bash
python excellon_to_gcode.py board.drl -b 1.0 -d 2.0
```

### Small bit for fine holes (0.8mm bit)
```bash
python excellon_to_gcode.py board.drl -b 0.8 -d 2.0 -f 80 -p 40
```

### Larger bit for mounting holes (3mm bit, 2mm depth)
```bash
python excellon_to_gcode.py board.drl -b 3.0 -d 2.0 -f 200 -p 100
```

### Custom output location
```bash
python excellon_to_gcode.py board.drl -o output/cnc_program.nc
```

### Compact output with arc moves (recommended!)
```bash
python excellon_to_gcode.py board.drl --use-arcs
```
This generates **85% smaller files** using G2/G3 arc moves instead of line segments!

## What the Program Does

### For Small Holes (≤ bit size)
- Moves to position
- Plunges straight down
- Retracts
- **Fast and efficient**

### For Large Holes (> bit size)
- Moves to hole center
- Spirals outward while descending
- Makes smooth circular cuts
- Accounts for bit radius automatically
- **Precise and clean**

### Arc Moves vs Linear Segments

**Default mode (linear segments):**
- Uses G1 line moves to approximate circles (36 segments per revolution)
- Compatible with all CNC controllers
- Larger file sizes

**Arc mode (`--use-arcs`):**
- Uses G2/G3 helical interpolation (true circular arcs)
- **85% smaller files!** (e.g., 24 KB → 3.7 KB)
- Smoother toolpaths
- Requires CNC controller with arc support (most modern controllers do)
- Perfect circles without segmentation

**When to use arc moves:**
- Your controller supports G2/G3 (most do!)
- You want smaller files for faster loading
- You want the smoothest possible circles

## Verify Before Running

1. **Simulate the G-code** using CAMotics, OpenSCAM, or your CNC software's simulator
2. **Check dimensions** - coordinates should match your design
3. **Verify safe heights** - ensure clearances work for your setup
4. **Test feed rates** - start conservative, increase as comfortable

## Getting Help

Run with `--help` for all options:
```bash
python excellon_to_gcode.py --help
```

## Example Output

When you run the program, you'll see:
```
Excellon to G-code Converter
==================================================
Tool T01: 0.8000 mm
Tool T02: 1.0000 mm
Tool T03: 3.0000 mm

Parsed 9 drill holes from 'board.drl'

Hole size summary:
  0.8000 mm: 3 holes
  1.0000 mm: 4 holes
  3.0000 mm: 2 holes

Generating G-code for 9 holes...

G-code generation complete!
  Straight drilled: 7 holes
  Spiral milled: 2 holes
  Output file: board.drl.nc

Conversion successful!
```

## Tips

- Start with default parameters and adjust based on results
- Use slower feed rates for harder materials
- Increase spindle speed for cleaner cuts in plastics
- Always secure your workpiece firmly
- Set your CNC zero point carefully before running

## Safety First! ⚠️

- **Always** simulate G-code before running on actual hardware
- **Never** leave CNC machine unattended while running
- **Wear** safety glasses and hearing protection
- **Secure** workpiece properly
- **Start** with conservative feed rates
- **Emergency stop** should be within reach

Ready to make some holes! 🔩
