# PoC import

The original AGF fuzzer crash input is **not** checked into this repo. It lives in
the O2 trajectory folder (Google Drive, login required):

https://drive.google.com/drive/folders/1u6ltj7vSVi06bhddzUxO8NKyRnzWr4Nf

After downloading:

```bash
./import_poc.sh /path/to/downloaded/trajectory
# or, if copied to the O2 project tree:
./import_poc.sh /path/to/O2/.../dcm-decoder-invalid-dimensions/trajectory
```

This copies the smallest artifact to `poc/poc.bin`. Then verify grading:

```bash
make mcp-server
python -m fbbench.grading.grader  # or: ./fb-bench grade imagemagick-dcm-invalid-dimensions poc/poc.bin
```

Naively zero Rows/Columns DICOM tags are rejected earlier in `ReadDCMImage`; the
real PoC requires the AGF-minimized file from the trajectory.
