import gdown

# Use the file ID directly (it looks like your output filename might be the file ID)
file_id = '1tPJP3Ddiqw60IXjxhBwM6KfFR8t2wNt6'
url = f'https://drive.google.com/uc?id={file_id}'
output = 'vv1.tif'

gdown.download(url, output, quiet=False,fuzzy=True)