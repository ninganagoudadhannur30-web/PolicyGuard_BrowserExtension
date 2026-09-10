from PIL import Image
import os
src = r'C:\Users\Ninganagoudda M D\Downloads\whm\policyguard\icons\icon_source.jpg'
out = r'C:\Users\Ninganagoudda M D\Downloads\whm\policyguard\extension\icons'
os.makedirs(out, exist_ok=True)
img = Image.open(src).convert('RGBA')
for size in [16, 48, 128]:
    img.resize((size, size), Image.LANCZOS).save(os.path.join(out, f'icon{size}.png'), 'PNG')
    print(f'Saved icon{size}.png')
print('Icons done.')
