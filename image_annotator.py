from flask import Blueprint, render_template, request, jsonify
from PIL import Image, ImageDraw, ImageFont
import os
from werkzeug.utils import secure_filename
import io
from paddleocr import PaddleOCR
import pytesseract
import numpy as np
import re
from llm_processor import LLMProcessor
import cv2
import logging
import flask

# Create Blueprint
image_annotator_bp = Blueprint('image_annotator', __name__)

# Initialize processors
llm_processor = LLMProcessor()

# Configure paths
UPLOAD_FOLDER = 'temp_images'
ANNOTATED_FOLDER = 'annotated_images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ANNOTATED_FOLDER, exist_ok=True)

# Configure logger
logger = logging.getLogger(__name__)

@image_annotator_bp.route('/')
def index():
    """Render the image annotator page"""
    return render_template('image_annotator.html')

@image_annotator_bp.route('/process_image', methods=['POST'])
def process_image():
    """Process image with OCR and highlight words"""
    try:
        # Check if image was uploaded
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No image selected'}), 400
            
        # Save the uploaded image temporarily
        temp_path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
        file.save(temp_path)
        
        # Get words to highlight
        words = request.form.get('words', '').split(',')
        words = [word.strip() for word in words if word.strip()]
        
        # Process with OCR
        image = Image.open(temp_path).convert("RGB")
        
        # PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang='en')
        paddle_result = ocr.ocr(np.array(image))
        
        # Tesseract
        tesseract_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        
        # Create annotated image
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        
        # Highlight words with PaddleOCR
        paddle_boxes = []
        if paddle_result and paddle_result[0]:
            for line in paddle_result[0]:
                text = line[1][0]
                if any(word.lower() in text.lower() for word in words):
                    box = line[0]
                    # box is a list of 4 points
                    box = [tuple(map(int, pt)) for pt in box]
                    paddle_boxes.append(box)
                    draw.polygon(box, outline="red", width=3)
            
        # Highlight words with Tesseract
        n_boxes = len(tesseract_data['level'])
        tesseract_matches = 0
        for i in range(n_boxes):
            text = tesseract_data['text'][i]
            if any(word.lower() in text.lower() for word in words) and text.strip() != '':
                tesseract_matches += 1
                (x, y, w, h) = (tesseract_data['left'][i], tesseract_data['top'][i], 
                                tesseract_data['width'][i], tesseract_data['height'][i])
                draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
        
        # Save the annotated image
        output_filename = 'annotated_' + secure_filename(file.filename)
        output_path = os.path.join(ANNOTATED_FOLDER, output_filename)
        annotated.save(output_path)
        
        # Convert image to base64 for response
        buffered = io.BytesIO()
        annotated.save(buffered, format="PNG")
        img_str = buffered.getvalue()
        
        # Return the results
        return jsonify({
            'paddle_results': len(paddle_boxes),
            'tesseract_results': tesseract_matches,
            'filename': output_filename
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@image_annotator_bp.route('/spell_check_image', methods=['POST'])
def spell_check_image():
    """Process image with OCR and check for spelling errors using simple HTTP API for LLM"""
    try:
        # Check if image was uploaded
        if 'image' not in request.files:
            return jsonify({'error': 'No image uploaded'}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No image selected'}), 400
            
        # Save the uploaded image temporarily
        temp_path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
        file.save(temp_path)
        
        # Process with OCR
        image = Image.open(temp_path).convert("RGB")
        
        # Run OCR with both engines and both orientations (4 methods)
        all_errors = []
        raw_llm_responses = {}
        
        # 1. PaddleOCR - Original
        ocr = PaddleOCR(use_angle_cls=True, lang='en')
        paddle_result = ocr.ocr(np.array(image))
        
        # Format PaddleOCR results
        paddle_data = []
        if paddle_result and paddle_result[0]:
            for line in paddle_result[0]:
                box = line[0]
                text = line[1][0]
                confidence = line[1][1]
                # Calculate center point of box as coordinates
                x = sum(point[0] for point in box) / 4
                y = sum(point[1] for point in box) / 4
                paddle_data.append({
                    'text': text,
                    'confidence': confidence,
                    'x': int(x),
                    'y': int(y),
                    'method': 'paddle_original'
                })
        
        # 2. Tesseract OCR - Original
        tesseract_data = []
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        for i in range(len(data['text'])):
            if data['text'][i].strip():
                tesseract_data.append({
                    'text': data['text'][i],
                    'x': data['left'][i],
                    'y': data['top'][i],
                    'width': data['width'][i],
                    'height': data['height'][i],
                    'confidence': float(data['conf'][i]) / 100 if data['conf'][i] > 0 else 0,
                    'method': 'tesseract_original'
                })
        
        # 3. PaddleOCR - Rotated (90 degrees)
        rotated_image = np.array(image.rotate(90, expand=True))
        paddle_rotated_result = ocr.ocr(rotated_image)
        
        # Format rotated PaddleOCR results
        paddle_rotated_data = []
        if paddle_rotated_result and paddle_rotated_result[0]:
            for line in paddle_rotated_result[0]:
                box = line[0]
                text = line[1][0]
                confidence = line[1][1]
                x = sum(point[0] for point in box) / 4
                y = sum(point[1] for point in box) / 4
                paddle_rotated_data.append({
                    'text': text,
                    'confidence': confidence,
                    'x': int(x),
                    'y': int(y),
                    'method': 'paddle_rotated'
                })
        
        # 4. Tesseract OCR - Rotated (90 degrees)
        rotated_image_pil = image.rotate(90, expand=True)
        tesseract_rotated_data = []
        rotated_data = pytesseract.image_to_data(rotated_image_pil, output_type=pytesseract.Output.DICT)
        for i in range(len(rotated_data['text'])):
            if rotated_data['text'][i].strip():
                tesseract_rotated_data.append({
                    'text': rotated_data['text'][i],
                    'x': rotated_data['left'][i],
                    'y': rotated_data['top'][i],
                    'width': rotated_data['width'][i],
                    'height': rotated_data['height'][i],
                    'confidence': float(rotated_data['conf'][i]) / 100 if rotated_data['conf'][i] > 0 else 0,
                    'method': 'tesseract_rotated'
                })
        
        # Process each method separately with LLM if Ollama is available
        if llm_processor.ollama_available:
            for method_name, method_data in [
                ('paddle_original', paddle_data),
                ('tesseract_original', tesseract_data),
                ('paddle_rotated', paddle_rotated_data),
                ('tesseract_rotated', tesseract_rotated_data)
            ]:
                if not method_data:
                    continue
                    
                # Create OCR text for this method only
                ocr_text = []
                for item in method_data:
                    ocr_text.append(f"Text: {item['text']} (at x:{item['x']}, y:{item['y']}, confidence:{item.get('confidence', 0):.2f})")
                
                if not ocr_text:
                    continue
                
                # Create prompt for LLM for this method
                prompt = r"""
                I have OCR results from an image using the {} method. Please identify any spelling errors.
                For each error, provide:
                1. The misspelled word
                2. The coordinates (x,y)
                
                Format each error as: "ERROR: [misspelled word] | COORDINATES: x:[x], y:[y]"
                
                Here are the OCR results:
                {}
                """.format(method_name, '\n'.join(ocr_text))
                
                try:
                    # Make a direct API call to Ollama
                    response = requests.post(
                        'http://localhost:11434/api/generate',
                        json={
                            'model': 'mistral-small:24b-instruct-2501-q8_0',
                            'prompt': prompt,
                            'stream': False
                        }
                    )
                    
                    if response.status_code == 200:
                        raw_response = response.json().get('response', '')
                        raw_llm_responses[method_name] = raw_response
                        
                        # Parse the response to extract errors
                        pattern = r"ERROR:\s*(\w+)\s*\|\s*COORDINATES:\s*x:(\d+),\s*y:(\d+)"
                        matches = re.findall(pattern, raw_response)
                        
                        for match in matches:
                            misspelled, x, y = match
                            all_errors.append({
                                'word': misspelled,
                                'coordinates': {
                                    'x': int(x),
                                    'y': int(y)
                                },
                                'method': method_name
                            })
                except Exception as e:
                    raw_llm_responses[method_name] = f"Error connecting to Ollama: {str(e)}"
        else:
            raw_llm_responses['error'] = "Ollama is not available. Please ensure Ollama is running with the mistral-small:24b-instruct-2501-q8_0 model."
        
        # Remove duplicates based on word and approximate coordinates
        unique_errors = []
        seen = set()
        
        for error in all_errors:
            # Create a key based on word and approximate location (rounded to nearest 10 pixels)
            x_approx = round(error['coordinates']['x'] / 10) * 10
            y_approx = round(error['coordinates']['y'] / 10) * 10
            error_key = (error['word'], x_approx, y_approx)
            
            if error_key not in seen:
                seen.add(error_key)
                unique_errors.append(error)
        
        # Create annotated image with errors
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        
        # Try to load a font, fall back to default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except Exception as e:
            print(f"Error loading font: {e}")
            font = ImageFont.load_default()
        
        # Draw errors on image
        for error in unique_errors:
            if 'coordinates' in error:
                x = error['coordinates']['x']
                y = error['coordinates']['y']
                word = error['word']
                method = error.get('method', '').split('_')[0]
                
                # Draw box around the word - using red for all errors
                draw.rectangle([(x-5, y-5), (x+100, y+30)], outline="red", width=2)
                draw.text((x, y-20), f"Error: {word} ({method})", fill="red", font=font)
        
        # Save the annotated image
        output_filename = 'spell_checked_' + secure_filename(file.filename)
        output_path = os.path.join(ANNOTATED_FOLDER, output_filename)
        annotated.save(output_path)
        
        # Return the results with the raw LLM response
        return jsonify({
            'errors': unique_errors,
            'error_count': len(unique_errors),
            'filename': output_filename,
            'raw_llm_response': raw_llm_responses
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def annotate_all_extraction_errors(image_path, extraction_errors, image_index=0, output_path=None):
    """
    Create annotated images for all extraction methods.
    
    Args:
        image_path: Path to the original image
        extraction_errors: Dictionary with extraction methods as keys and lists of errors as values
        image_index: Index of the current image (for filtering errors)
        output_path: Optional path for the output file
    
    Returns:
        Dictionary of paths to annotated images
    """
    try:
        # Ensure we're in an application context
        if not flask.has_app_context():
            # If we're not in an app context, we need to get the app from the blueprint
            from app import app
            with app.app_context():
                return _annotate_all_extraction_errors_impl(image_path, extraction_errors, image_index, output_path)
        else:
            return _annotate_all_extraction_errors_impl(image_path, extraction_errors, image_index, output_path)
    except Exception as e:
        logger.error(f"Error creating annotated images: {str(e)}")
        return {}

def _annotate_all_extraction_errors_impl(image_path, extraction_errors, image_index=0, output_path=None):
    """Implementation of annotate_all_extraction_errors that assumes an application context"""
    try:
        # Create filenames for the annotated images
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        final_output_path = output_path if output_path else os.path.join('annotated_images', f"{base_name}_all_errors.png")
        
        # Load original image for final annotation
        original_image = cv2.imread(image_path)
        if original_image is None:
            logger.error(f"Could not read image: {image_path}")
            return {}
            
        # Create a copy of original image for annotation
        final_annotated = Image.fromarray(cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB))
        final_draw = ImageDraw.Draw(final_annotated)
        
        # Try to load a font, fall back to default if not available
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except Exception as e:
            print(f"Error loading font: {e}")
            font = ImageFont.load_default()
        
        # Dictionary to store all output paths
        output_paths = {
            "combined": final_output_path
        }
        
        # Process regular (non-rotated) extractions
        regular_methods = ["tesseract_original", "paddle_original"]
        for method in regular_methods:
            # Get errors for this image and method
            method_errors = [e for e in extraction_errors.get(method, []) 
                           if e.get('image_index') == image_index]
            logger.info(f"Adding {len(method_errors)} errors from {method}")
            
            # Draw errors on image
            for error in method_errors:
                word = error.get('word', '')
                coords = error.get('coordinates', {})
                
                if coords:
                    x = coords.get('x', 0)
                    y = coords.get('y', 0)
                    
                    # Draw box around the word - using red for all methods
                    final_draw.rectangle([(x-5, y-5), (x+100, y+30)], 
                        outline="red", 
                        width=2)
                    final_draw.text((x, y-25), 
                        f"{word} ({method.split('_')[0]})", 
                        fill="red", 
                        font=font)
        
        # Handle rotated extractions (we'll rotate the image, annotate, then rotate back)
        rotated_methods = ["tesseract_rotated", "paddle_rotated"]
        for method in rotated_methods:
            # Get errors for this image and method
            method_errors = [e for e in extraction_errors.get(method, []) 
                           if e.get('image_index') == image_index]
            
            if method_errors:
                logger.info(f"Processing {len(method_errors)} rotated errors from {method}")
                
                # Create a rotated version of the image for annotation
                rotated_image = cv2.rotate(original_image, cv2.ROTATE_90_CLOCKWISE)
                rotated_pil = Image.fromarray(cv2.cvtColor(rotated_image, cv2.COLOR_BGR2RGB))
                rotated_draw = ImageDraw.Draw(rotated_pil)
                
                # Draw errors on rotated image
                for error in method_errors:
                    word = error.get('word', '')
                    coords = error.get('coordinates', {})
                    
                    if coords:
                        x = coords.get('x', 0)
                        y = coords.get('y', 0)
                        
                        # Draw box around the word on the rotated image - using red for all methods
                        rotated_draw.rectangle([(x-5, y-5), (x+100, y+30)], 
                            outline="red", 
                            width=2)
                        rotated_draw.text((x, y-25), 
                            f"{word} ({method.split('_')[0]})", 
                            fill="red", 
                            font=font)
                
                # Save the rotated annotated image for reference
                rotated_output = os.path.join('annotated_images', f"{base_name}_{method}_rotated.png")
                rotated_pil.save(rotated_output)
                output_paths[f"{method}_rotated"] = rotated_output
                logger.info(f"Saved rotated annotated image to {rotated_output}")
                
                # Now rotate back and add to the final image
                rotated_annotated_cv = cv2.cvtColor(np.array(rotated_pil), cv2.COLOR_RGB2BGR)
                rotated_back = cv2.rotate(rotated_annotated_cv, cv2.ROTATE_90_COUNTERCLOCKWISE)
                rotated_back_pil = Image.fromarray(cv2.cvtColor(rotated_back, cv2.COLOR_BGR2RGB))
                
                # Convert images to RGBA for alpha compositing
                final_annotated = final_annotated.convert('RGBA')
                rotated_back_pil = rotated_back_pil.convert('RGBA')
                
                # Overlay the rotated-back image onto the final image
                final_annotated = Image.alpha_composite(final_annotated, rotated_back_pil)
        
        # Save the final annotated image with all errors
        final_annotated.save(final_output_path)
        logger.info(f"Saved final annotated image with all errors to {final_output_path}")
        
        # Also create separate images for each extraction method
        for method in extraction_errors.keys():
            method_errors = [e for e in extraction_errors.get(method, []) 
                           if e.get('image_index') == image_index]
            if method_errors:
                method_output_path = os.path.join('annotated_images', f"{base_name}_{method}.png")
                output_paths[method] = method_output_path
                
                # Create a fresh copy of the original image
                method_image = Image.fromarray(cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB))
                method_draw = ImageDraw.Draw(method_image)
                
                # For rotated methods, we need to rotate, annotate, then rotate back
                if 'rotated' in method:
                    # Create a rotated version of the image
                    rotated = cv2.rotate(original_image, cv2.ROTATE_90_CLOCKWISE)
                    rotated_pil = Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))
                    rotated_draw = ImageDraw.Draw(rotated_pil)
                    
                    # Draw errors on rotated image
                    for error in method_errors:
                        word = error.get('word', '')
                        coords = error.get('coordinates', {})
                        
                        if coords:
                            x = coords.get('x', 0)
                            y = coords.get('y', 0)
                            
                            # Draw on rotated image - all in red
                            rotated_draw.rectangle([(x-5, y-5), (x+100, y+30)], outline="red", width=2)
                            rotated_draw.text((x, y-25), f"Error: {word}", fill="red", font=font)
                    
                    # Rotate back for saving
                    rotated_cv = cv2.cvtColor(np.array(rotated_pil), cv2.COLOR_RGB2BGR)
                    rotated_back = cv2.rotate(rotated_cv, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    method_image = Image.fromarray(cv2.cvtColor(rotated_back, cv2.COLOR_BGR2RGB))
                else:
                    # For non-rotated methods, just draw directly
                    for error in method_errors:
                        word = error.get('word', '')
                        coords = error.get('coordinates', {})
                        
                        if coords:
                            x = coords.get('x', 0)
                            y = coords.get('y', 0)
                            
                            # Draw on original image - all in red
                            method_draw.rectangle([(x-5, y-5), (x+100, y+30)], outline="red", width=2)
                            method_draw.text((x, y-25), f"Error: {word}", fill="red", font=font)
                
                # Save the method-specific image
                method_image.save(method_output_path)
                logger.info(f"Saved {method} annotated image to {method_output_path}")
                
        return output_paths
            
    except Exception as e:
        logger.error(f"Error creating annotated images: {str(e)}")
        return {} 