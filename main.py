from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
from datetime import datetime
import socket
import pytesseract
from PIL import Image
import cv2
import numpy as np
import re
from concurrent.futures import ThreadPoolExecutor
from gtts import gTTS
from fastapi.responses import FileResponse
import threading
import time
import glob

app = FastAPI()

# Allow CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Folder to save uploaded images
UPLOAD_FOLDER = "uploaded_images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Folder to save TTS audio
AUDIO_FOLDER = "output_audio"
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# Store OCR and TTS results
processing_results = {}
executor = ThreadPoolExecutor(max_workers=3)

def extract_text_from_image(image_path):
    """Extract text from image using pytesseract with enhanced preprocessing and cropping"""
    try:
        image = cv2.imread(image_path)
        if image is None:
            return "Error: Could not read image"

        # 🪄 Crop image to remove header, side UI noise
        h, w, _ = image.shape
        cropped = image[int(h*0.2):int(h*0.95), int(w*0.05):int(w*0.95)]

        # Preprocess image
        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)

        pil_image = Image.fromarray(cleaned)

        # Multiple PSM configs for robust text extraction
        configs = [
            r'--oem 3 --psm 6',
            r'--oem 3 --psm 8',
            r'--oem 3 --psm 13'
        ]

        all_text = []
        for config in configs:
            try:
                text = pytesseract.image_to_string(pil_image, config=config)
                if text.strip():
                    all_text.append(text.strip())
            except:
                continue

        if all_text:
            combined_text = ' '.join(all_text)
            cleaned_text = ' '.join(combined_text.split())
            cleaned_text = re.sub(r'[^\x00-\x7F]+', '', cleaned_text)  # remove non-ASCII
            return cleaned_text
        else:
            return "No text detected in the image"

    except Exception as e:
        return f"OCR Error: {str(e)}"

def generate_audio_from_text(text, base_filename):
    """Generate audio file from text using gTTS"""
    try:
        print(f"🎵 Generating audio for: {base_filename}.mp3")
        print(f"📝 Text: {text[:100]}...")  # Show first 100 chars
        
        # Create gTTS object with English language
        tts = gTTS(text=text, lang='en', slow=False)
        
        # Save audio file
        audio_path = os.path.join(AUDIO_FOLDER, f"{base_filename}.mp3")
        tts.save(audio_path)
        
        # Verify file was created
        if os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            print(f"✅ Audio generated successfully: {audio_path} ({file_size} bytes)")
            return audio_path
        else:
            print(f"❌ Audio file not created: {audio_path}")
            return None
            
    except Exception as e:
        print(f"❌ Audio generation error: {str(e)}")
        return None

def process_image_complete(base_filename, file_path):
    """Complete processing pipeline: OCR + TTS in single function"""
    try:
        print(f"\n🔄 Starting complete processing for: {base_filename}")
        
        # Step 1: OCR Processing
        print("📝 Step 1: Extracting text from image...")
        extracted_text = extract_text_from_image(file_path)
        
        # Update status
        processing_results[base_filename + ".jpg"] = {
            "status": "ocr_completed",
            "text": extracted_text,
            "ocr_timestamp": datetime.now().isoformat(),
            "audio_status": "pending"
        }
        
        print("📝 Extracted Text:")
        print("=" * 50)
        print(extracted_text)
        print("=" * 50)
        
        # Step 2: Audio Generation (if text is valid)
        if extracted_text and not extracted_text.strip().lower().startswith("error") and extracted_text != "No text detected in the image":
            print("🎵 Step 2: Generating audio from text...")
            
            # Update status
            processing_results[base_filename + ".jpg"]["audio_status"] = "generating"
            
            # Generate audio
            audio_path = generate_audio_from_text(extracted_text, base_filename)
            
            if audio_path:
                # Update final status
                processing_results[base_filename + ".jpg"].update({
                    "status": "completed",
                    "audio_status": "completed",
                    "audio_path": audio_path,
                    "audio_timestamp": datetime.now().isoformat()
                })
                print(f"✅ Complete processing finished for: {base_filename}")
            else:
                # Audio generation failed
                processing_results[base_filename + ".jpg"].update({
                    "status": "ocr_only",
                    "audio_status": "failed",
                    "audio_error": "Audio generation failed"
                })
                print(f"⚠ OCR completed but audio generation failed for: {base_filename}")
        else:
            # No valid text for audio generation
            processing_results[base_filename + ".jpg"].update({
                "status": "ocr_only",
                "audio_status": "skipped",
                "audio_error": "No valid text for audio generation"
            })
            print(f"⚠ OCR completed but no valid text for audio generation: {base_filename}")
            
    except Exception as e:
        processing_results[base_filename + ".jpg"] = {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        print(f"❌ Processing error for {base_filename}: {str(e)}")

@app.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload image and start complete processing pipeline"""
    try:
        now = datetime.now()
        # Generate a base filename without extension
        base_filename = f"ESP32_{now.year}{now.month:02}{now.day:02}{now.hour:02}{now.minute:02}_{now.second:02}"
        file_path = os.path.join(UPLOAD_FOLDER, base_filename + ".jpg")

        # Save uploaded file
        with open(file_path, "wb") as f:
            f.write(await file.read())

        print(f"✅ Image saved: {file_path}")

        # Initialize processing status
        processing_results[base_filename + ".jpg"] = {
            "status": "processing", 
            "timestamp": datetime.now().isoformat(),
            "filename": base_filename + ".jpg"
        }
        
        # Start complete processing pipeline in background
        executor.submit(process_image_complete, base_filename, file_path)

        return {
            "status": "success",
            "filename": base_filename + ".jpg",
            "message": "Image uploaded successfully. OCR and TTS processing started automatically.",
            "processing_status": "started"
        }
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        return {"error": str(e)}

@app.get("/processing-result/{filename}")
async def get_processing_result(filename: str):
    """Get complete processing result (OCR + TTS) for a specific file"""
    if filename in processing_results:
        result = processing_results[filename].copy()
        
        # Add file existence checks
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        result["image_exists"] = os.path.exists(image_path)
        
        if result.get("audio_path"):
            result["audio_exists"] = os.path.exists(result["audio_path"])
        
        return result
    else:
        return {"status": "not_found", "message": "Processing result not found for this filename"}

@app.get("/processing-results")
async def get_all_processing_results():
    """Get all processing results with file existence checks"""
    results = {}
    for filename, result in processing_results.items():
        result_copy = result.copy()
        
        # Add file existence checks
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        result_copy["image_exists"] = os.path.exists(image_path)
        
        if result.get("audio_path"):
            result_copy["audio_exists"] = os.path.exists(result["audio_path"])
        
        results[filename] = result_copy
    
    return results

@app.get("/audio/{filename}")
async def get_audio_file(filename: str):
    """Download audio file for a specific filename"""
    audio_path = os.path.join(AUDIO_FOLDER, filename)
    if not os.path.exists(audio_path):
        return {"status": "error", "message": "Audio file not found"}
    return FileResponse(audio_path, media_type="audio/mpeg", filename=filename)

@app.get("/text/{filename}")
async def get_text_only(filename: str):
    """Get only the extracted text for a specific filename"""
    if filename not in processing_results:
        return {"status": "not_found", "message": "Processing result not found for this filename"}
    
    result = processing_results[filename]
    if result.get("status") in ["processing", "error"]:
        return {"status": "not_ready", "message": "Text extraction not yet completed"}
    
    return {
        "filename": filename,
        "text": result.get("text", ""),
        "status": result.get("status"),
        "timestamp": result.get("ocr_timestamp")
    }

# Legacy endpoints for backward compatibility
@app.get("/ocr-result/{filename}")
async def get_ocr_result(filename: str):
    return await get_processing_result(filename)

@app.get("/ocr-results")
async def get_all_ocr_results():
    return await get_all_processing_results()

@app.get("/tts/{filename}")
async def tts_from_ocr(filename: str):
    return await get_audio_file(filename)

@app.get("/latest-audio")
async def get_latest_audio():
    """Serve the most recently generated audio file."""
    audio_files = sorted(
        glob.glob(os.path.join(AUDIO_FOLDER, "*.mp3")),
        key=os.path.getmtime,
        reverse=True
    )
    if not audio_files:
        return {"status": "not_found", "message": "No audio files found"}
    latest_audio = audio_files[0]
    filename = os.path.basename(latest_audio)
    return FileResponse(latest_audio, media_type="audio/mpeg", filename=filename)

@app.get("/latest-audio-filename")
async def get_latest_audio_filename():
    """Return the filename of the most recently generated audio file."""
    audio_files = sorted(
        glob.glob(os.path.join(AUDIO_FOLDER, "*.mp3")),
        key=os.path.getmtime,
        reverse=True
    )
    if not audio_files:
        return {"status": "not_found", "message": "No audio files found"}
    latest_audio = os.path.basename(audio_files[0])
    return {"filename": latest_audio}

if __name__ == "__main__":
    import uvicorn
    ip = socket.gethostbyname(socket.gethostname())
    print(f"📡 Your local IP address: http://{ip}:8000")
    print("🔍 OCR + TTS Integrated Processing Enabled!")
    print("📝 Text extraction and audio generation happen automatically in single pipeline")
    print("⚡ Asynchronous processing enabled - no delays!")
    print("🎵 Audio files are generated automatically after text extraction")
    uvicorn.run("main:app", host="0.0.0.0", port=8000)