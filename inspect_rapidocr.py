import pathlib

try:
    import rapidocr_onnxruntime
    print('package', rapidocr_onnxruntime)
    p = pathlib.Path(rapidocr_onnxruntime.__file__).resolve().parent
    print('path', p)
    py_files = [x.name for x in p.iterdir() if x.is_file() and x.suffix == '.py' and x.name != '__init__.py']
    print('py files', py_files)
    subdirs = [x.name for x in p.iterdir() if x.is_dir()]
    print('subdirs', subdirs)
    import ch_ppocr_v3_det
    print('ch_ppocr_v3_det file', pathlib.Path(ch_ppocr_v3_det.__file__).resolve())
    attrs = [a for a in dir(ch_ppocr_v3_det) if 'TextDetector' in a or 'Detector' in a or 'text' in a.lower()]
    print('attrs', attrs)
except Exception as exc:
    import traceback
    traceback.print_exc()
