import numpy as np
from extra.utils import fetch, download_file, get_child
from examples.yolov8 import YOLOv8, get_variant_multiples, preprocess, postprocess, label_predictions
from pathlib import Path
import unittest
import io, cv2, os
import onnxruntime as ort
import ultralytics
from tinygrad.state import safe_load, load_state_dict

class TestYOLOv8(unittest.TestCase):
  def test_all_load_weights(self):
    for variant in ['n', 's', 'm', 'l', 'x']:
      weights_location = Path(__file__).parent.parent.parent / "weights" / f'yolov8{variant}.safetensors'
      download_file(f'https://gitlab.com/r3sist/yolov8_weights/-/raw/master/yolov8{variant}.safetensors', weights_location)
      
      depth, width, ratio = get_variant_multiples(variant) 
      TinyYolov8 = YOLOv8(w=width, r=ratio, d=depth, num_classes=80)     
      state_dict = safe_load(weights_location)
      load_state_dict(TinyYolov8, state_dict)
      print(f'successfully loaded weights for yolov{variant}')
                
  def test_predictions(self):
    test_image_urls = ['https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/bus.jpg', 'https://www.aljazeera.com/wp-content/uploads/2022/10/2022-04-28T192650Z_1186456067_UP1EI4S1I0P14_RTRMADP_3_SOCCER-ENGLAND-MUN-CHE-REPORT.jpg']
    variant = 'n'
    weights_location = Path(__file__).parent.parent.parent / "weights" / f'yolov8{variant}.safetensors'
    depth, width, ratio = get_variant_multiples(variant) 
    TinyYolov8 = YOLOv8(w=width, r=ratio, d=depth, num_classes=80) 
    state_dict = safe_load(weights_location)
    load_state_dict(TinyYolov8, state_dict)
    
    for i in range(len(test_image_urls)):
      img_stream = io.BytesIO(fetch(test_image_urls[i]))
      img = cv2.imdecode(np.frombuffer(img_stream.read(), np.uint8), 1)
      test_image = preprocess([img])
      predictions = TinyYolov8(test_image)
      post_predictions = postprocess(preds=predictions, img=test_image, orig_imgs=[img])
      labels = label_predictions(post_predictions)
      assert labels == {5: 1, 0: 4, 11: 1} if i == 0 else labels == {0: 13, 29: 1, 32: 1}
      
  def test_forward_pass_torch_onnx(self):
    variant = 'n'
    weights_location_onnx = Path(__file__).parent.parent.parent / "weights" / f'yolov8{variant}.onnx' 
    weights_location_pt = Path(__file__).parent.parent.parent / "weights" / f'yolov8{variant}.pt' 
    weights_location = Path(__file__).parent.parent.parent / "weights" / f'yolov8{variant}.safetensors' 

    download_file(f'https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8{variant}.pt', weights_location_pt)
    # the ultralytics export prints a lot of unneccesary things
    if not os.path.isfile(weights_location_onnx):
      model = ultralytics.YOLO(model=weights_location_pt, task='Detect')  
      model.export(format="onnx",imgsz=[640, 480]) 

    depth, width, ratio = get_variant_multiples(variant) 
    TinyYolov8 = YOLOv8(w=width, r=ratio, d=depth, num_classes=80) 
    state_dict = safe_load(weights_location)
    load_state_dict(TinyYolov8, state_dict)
    
    image_location = [np.frombuffer(io.BytesIO(fetch('https://raw.githubusercontent.com/ultralytics/yolov5/master/data/images/bus.jpg')).read(), np.uint8)]
    orig_image = [cv2.imdecode(image_location[0], 1)]
    
    input_image = preprocess(orig_image)
    
    onnx_session = ort.InferenceSession(weights_location_onnx)
    onnx_input_name = onnx_session.get_inputs()[0].name
    onnx_output_name = onnx_session.get_outputs()[0].name
    onnx_output = onnx_session.run([onnx_output_name], {onnx_input_name: input_image.cpu().numpy()})

    tiny_output = TinyYolov8(input_image)
    
    # currently rtol is 0.025 because there is a 1-2% difference in our predictions 
    # because of the zero padding in SPPF module (line 280) maxpooling layers rather than the -infinity in torch. 
    # This difference does not make a difference "visually". 
    np.testing.assert_allclose(onnx_output[0], tiny_output.cpu().numpy(), atol=5e-4, rtol=0.025)
    
if __name__ == '__main__':
    unittest.main()
    