import numpy as np, sys

for f in sys.argv[1:]:
    z = np.load(f, allow_pickle=True)
    print(f)
    print([(k, z[k].shape, z[k].dtype) for k in z.files])
