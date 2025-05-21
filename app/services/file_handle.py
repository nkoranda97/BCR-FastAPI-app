import os
import zipfile
import shutil
from typing import List
from fastapi import HTTPException, UploadFile
from fastapi.responses import RedirectResponse


async def file_extraction(
    files: List[UploadFile], project_folder: str, landing_page: str
) -> List[str]:
    """
    Extract and validate uploaded zip files containing sample data

    Args:
        files: List of uploaded zip files
        project_folder: Path to the project folder
        landing_page: URL to redirect to in case of errors

    Returns:
        List of paths to extracted sample folders

    Raises:
        HTTPException: If there are issues with the zip files or their contents
    """
    sample_folders = []

    for file in files:
        filename = file.filename
        if not filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        # Validate file extension
        if not filename.lower().endswith(".zip"):
            raise HTTPException(
                status_code=400,
                detail=f"File {filename} is not a zip file. Please upload a zip file.",
            )

        zip_path = os.path.join(project_folder, filename)

        # Save the uploaded file with size tracking
        try:
            # Get the file size from the upload
            file_size = 0
            with open(zip_path, "wb") as buffer:
                while chunk := await file.read(8192):  # Read in chunks
                    buffer.write(chunk)
                    file_size += len(chunk)

            # Verify the file was saved correctly
            if not os.path.exists(zip_path):
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save file {filename}. File does not exist after save.",
                )

            saved_size = os.path.getsize(zip_path)
            if saved_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {filename} was saved as empty (0 bytes). Original size: {file_size} bytes.",
                )

            if saved_size != file_size:
                raise HTTPException(
                    status_code=500,
                    detail=f"File size mismatch. Original: {file_size} bytes, Saved: {saved_size} bytes.",
                )

        except Exception as e:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            raise HTTPException(
                status_code=500, detail=f"Failed to save file {filename}: {str(e)}"
            )

        # Validate zip file with detailed error checking
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Test zip file integrity
                test_result = zip_ref.testzip()
                if test_result is not None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Zip file {filename} is corrupted. First bad file: {test_result}",
                    )

                # Get file list
                file_list = zip_ref.namelist()
                if not file_list:
                    raise HTTPException(
                        status_code=400, detail=f"Zip file {filename} is empty."
                    )

                # Extract files
                zip_ref.extractall(project_folder)

            # Remove the zip file after successful extraction
            os.remove(zip_path)

            extracted_folder = filename.rsplit(".", 1)[0]
            sample_folder = os.path.join(project_folder, extracted_folder)

            # Check if the extracted folder exists
            if not os.path.exists(sample_folder):
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to extract {filename}. The expected folder {extracted_folder} was not created.",
                )

            sample_folders.append(sample_folder)

            # Validate contents
            files_in_folder = os.listdir(sample_folder)
            if not files_in_folder:
                raise HTTPException(
                    status_code=400,
                    detail=f"Extracted folder {extracted_folder} is empty.",
                )

            if not any(f.endswith(".csv") for f in files_in_folder):
                raise HTTPException(
                    status_code=400,
                    detail=f"Folder {extracted_folder} does not contain any .csv files.",
                )

            if not any(f.endswith(".fasta") for f in files_in_folder):
                raise HTTPException(
                    status_code=400,
                    detail=f"Folder {extracted_folder} does not contain any .fasta files.",
                )

            # Rename files to standardized names
            for file in files_in_folder:
                if file.endswith(".csv"):
                    old_path = os.path.join(sample_folder, file)
                    new_path = os.path.join(
                        sample_folder, "filtered_contig_annotations.csv"
                    )
                    os.rename(old_path, new_path)
                elif file.endswith(".fasta"):
                    old_path = os.path.join(sample_folder, file)
                    new_path = os.path.join(sample_folder, "filtered_contig.fasta")
                    os.rename(old_path, new_path)

        except zipfile.BadZipFile as e:
            # Clean up in case of error
            if os.path.exists(zip_path):
                os.remove(zip_path)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to unzip file {filename}. Error: {str(e)}",
            )
        except Exception as e:
            # Clean up in case of error
            if os.path.exists(zip_path):
                os.remove(zip_path)
            if os.path.exists(sample_folder):
                shutil.rmtree(sample_folder)
            raise HTTPException(
                status_code=500,
                detail=f"An error occurred while processing file {filename}: {str(e)}",
            )

    return sample_folders
