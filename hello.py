from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from PIL import Image

processor=TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
model=VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

img=Image.open("test_write.jpeg").convert("RGB")
pixel_values=processor(img, return_tensors="pt").pixel_values

generated_ids=model.generate(pixel_values)
text=processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
print(text)
