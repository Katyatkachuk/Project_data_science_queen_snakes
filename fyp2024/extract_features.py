
import numpy as np
import cv2

from statistics import mean
import os
import csv
from scipy import ndimage
from sklearn.cluster import KMeans
import pandas as pd
from os.path import exists


def extract_features(image,mask):

    """
    Args:
        image: The image to process.
        mask: its mask.

    Returns:
        array with features array
        
    """

    # Initializing an array to store feature values
    num_features=4
    features = np.zeros(num_features, dtype=np.float16)
    
    # Feature 1: Assymetry
    features[0] = calculate_symmetry_level(check_symmetry(mask))
    
    # Feature 2: Colours
    features[1] = color_analysis(image,mask)
    
    # Feature 3: Dots and Globules
    if (features[1] >= 2):
        features[2] = detect_dots(image,mask)
    else :
        features[2] = 0

    # Feature 4: Compactness
    features[3] = calculate_compactness(mask)
    
    return features



def check_symmetry(mask):

    """
     Args:
        image: The image to process.
        mask: Its mask.

    Returns:
        level of assymetry from 1 to 3

    """
    # Load the mask
    # mask = cv2.imread(image, cv2.IMREAD_GRAYSCALE)
    # Resize mask to match image size if they don't match

    area = np.sum(mask)  # defect area
    com = ndimage.center_of_mass(mask)  # find the center of mass
    com = (int(com[0]), int(com[1]))  # convert coordinates to integers

    # Create a mask with the defect contour
    brush = ndimage.generate_binary_structure(2, 1)  # create a brush for erosion
    eroded = ndimage.binary_erosion(mask, brush)  # mask after erosion
    border = mask - eroded  # defect contour
    rows, cols = np.nonzero(border)  # find contour coordinates
    coords = zip(rows, cols)  # collect coordinates

    # Find the distance from the center of mass to each contour pixel
    dist_list = []
    for r, c in coords:
        dist_list.append(int(np.sqrt((r - com[0]) ** 2 + (c - com[1]) ** 2)))  # Euclidean distance

    # Maximum distance from the center of mass to the mask edge + 10 pixels
    max_dist = max(dist_list) + 10

    # Crop the mask to a square with a side of max_dist+10 with the center at com
    r1 = com[0] - max_dist  # lower boundary for row
    r2 = com[0] + max_dist  # upper boundary for row
    c1 = com[1] - max_dist  # left boundary for column
    c2 = com[1] + max_dist  # right boundary for column

    # If any of the boundaries go beyond the image boundaries,
    # add empty rows/columns to the mask up to a distance of max_dist+10
    # this keeps com in the center and the mask square
    if r1 < 0:
        mask = np.append(np.zeros([abs(r1), mask.shape[1]]), mask, 0)
        r2 += abs(r1)
        r1 = 0
    if c1 < 0:
        mask = np.append(np.zeros([mask.shape[0], abs(c1)]), mask, 1)
        c2 += abs(c1)
        c1 = 0
    if r2 > mask.shape[0]:
        mask = np.append(mask, np.zeros([r2 - mask.shape[0], mask.shape[1]]), 0)
        r2 = mask.shape[0]
    if c2 > mask.shape[1]:
        mask = np.append(mask, np.zeros([mask.shape[0], c2 - mask.shape[1]]), 1)
        c2 = mask.shape[1]

    # Make a square around the defect
    new_mask = mask[r1:r2, c1:c2]

    # Check and correct if new_mask is odd along one of the axes
    if new_mask.shape[0] % 2 != 0:
        new_mask = np.append(new_mask, np.zeros([1, new_mask.shape[1]]), 0)
    if new_mask.shape[1] % 2 != 0:
        new_mask = np.append(new_mask, np.zeros([new_mask.shape[0], 1]), 1)

    def split_vertical():
        # Check symmetry along the vertical axis (left-right)
        mask_left, mask_right = np.split(new_mask, 2, axis=1)
        mask_left = mask_left.astype(np.int8)
        mask_right = mask_right.astype(np.int8)
        reflect_mask_left = np.flip(mask_left, axis=1)
        reflect_mask_left = reflect_mask_left.astype(np.int8)
        sym = np.abs(mask_right - reflect_mask_left)
        ratio = 2 * np.sum(sym) / area
        return ratio

    def split_horizontal():
        # Check symmetry along the horizontal axis (up-down)
        mask_up, mask_down = np.split(new_mask, 2, axis=0)
        mask_up = mask_up.astype(np.int8)
        mask_down = mask_down.astype(np.int8)
        reflect_mask_up = np.flip(mask_up, axis=0)
        reflect_mask_up = reflect_mask_up.astype(np.int8)
        sym = np.abs(mask_down - reflect_mask_up)
        ratio = 2 * np.sum(sym) / area
        return ratio

    def split_downwards_diagonal():
        # Check symmetry along the diagonal (left-down)
        mask_up = np.triu(new_mask)
        mask_up = mask_up.astype(np.int8)
        rotate_mask_up = np.transpose(mask_up)
        rotate_mask_up = rotate_mask_up.astype(np.int8)
        mask_down = np.tril(new_mask)
        mask_down = mask_down.astype(np.int8)
        sym = np.abs(mask_down - rotate_mask_up)
        ratio = 2 * np.sum(sym) / area
        return ratio

    def split_upwards_diagonal():
        # Check symmetry along the diagonal (left-up)
        new_new_mask = np.flip(new_mask, axis=1)
        mask_up = np.triu(new_new_mask)
        mask_up = mask_up.astype(np.int8)
        rotate_mask_up = np.transpose(mask_up)
        rotate_mask_up = rotate_mask_up.astype(np.int8)
        mask_down = np.tril(new_new_mask)
        mask_down = mask_down.astype(np.int8)
        sym = np.abs(mask_down - rotate_mask_up)
        ratio = 2 * np.sum(sym) / area
        return ratio

    ratio = mean([split_vertical(), split_horizontal(), split_downwards_diagonal(), split_upwards_diagonal()])
    return ratio


def calculate_symmetry_level(asymmetry_ratio):
    if asymmetry_ratio < 0.1:
        return 1  # symmetric
    elif asymmetry_ratio < 0.3:
        return 2  # symmetric along only one axis
    else:
        return 3  # asymmetric



def process_images_with_masks(image, mask):
    """
    Args:
        image: The image to process.
        mask: Its mask.

    Returns:
        image with green circles around the detected dots merged with mask
    """

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Improve contrast with CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    equalized = clahe.apply(gray)

    # Apply median blur
    blur = cv2.medianBlur(equalized, 5)

    # Use adaptive thresholding
    thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 25, 8)

    # Morphological operations
    kernel = np.ones((3, 3), np.uint8)
    morphed = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # Find contours with area filter
    contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    larger_dot_area_threshold = 100  

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > larger_dot_area_threshold:
            # Check if contour is approximately circular
            perimeter = cv2.arcLength(cnt, True)
            circularity = 4 * np.pi * (area / (perimeter * perimeter))
            if circularity > 0.1:
                # Check if contour touches border
                x, y, w, h = cv2.boundingRect(cnt)
                if x > 1 and y > 1 and (x + w) < image.shape[1] - 1 and (y + h) < image.shape[0] - 1:
                    # Draw circle for each dot
                    cv2.circle(image, (int(x + w / 2), int(y + h / 2)), int((w + h) / 2), (0, 255, 0), 2)

    # Resize mask to match image size if they don't match
    if image.shape[:2] != mask.shape:
        mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)

    # Apply mask (mask should be 255 for the regions to keep)
    result = cv2.bitwise_and(image, image, mask=mask)

    return result
 

def detect_dots(image,mask):

    image_with_dots=process_images_with_masks(image, mask)
    #Detects green circles in an image.
    
    """
    Args:
        image: The image to process.
        mask: Its mask.

    Returns:
        1 if a green circle is found, 0 otherwise.
    
    """
    # Convert the image to HSV color space
    hsv = cv2.cvtColor(image_with_dots, cv2.COLOR_BGR2HSV)

    # Define the lower and upper bounds for green color in HSV
    lower_green = np.array([40, 50, 50], dtype="uint8")
    upper_green = np.array([80, 255, 255], dtype="uint8")

    # Create a mask for green pixels
    mask = cv2.inRange(hsv, lower_green, upper_green)

    # Apply Hough circle transform to find circles in the mask
    circles = cv2.HoughCircles(mask, cv2.HOUGH_GRADIENT, 1, 20,
                                param1=50, param2=30, minRadius=10, maxRadius=200)

    # Check if any circles were found
    if circles is not None:
    # Convert the circles from a tuple to a NumPy array
        circles = np.uint16(np.around(circles[0, :]))

        # Draw the detected circles on the original image (optional)
        for (x, y, r) in circles:
            cv2.circle(image, (x, y), r, (0, 255, 0), 2)

        # Return 1 if at least one green circle is found
        return 1
    else:
        # Return 0 if no green circles are found
        return 0
    

def calculate_compactness(image):
    """
    Args:

        mask: Mask of the image.

    Returns:
        level of compactness

    """

    # Threshold the image to create a binary mask
    _, thresh = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Find contours in the binary mask
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Check if contours were found
    if len(contours) == 0:
        # No contours found, handle this case
        print("No contours found in the image.")
        return None

    # Select the largest contour
    contour = max(contours, key=cv2.contourArea)

    # Calculate area and perimeter of the contour
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, True)

    # Calculate compactness
    compactness = (perimeter ** 2) / (4 * np.pi * area)

    return compactness




def color_analysis(image, mask):
    """
    Args:
        #image: The image to process.
        #mask: Its mask.

    #Returns:
        # Number of colors detected from 0 to 6
    """
    # Convert image to HSV color space
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Define color ranges for each shade
    color_ranges = {
        'white': ([0, 0, 150], [180, 50, 255]),  # HSV range for white
        'red': ([0, 50, 50], [5, 255, 255]),  # HSV range for red (lower range)
        'red2': ([170, 50, 50], [180, 255, 255]),  # HSV range for red (upper range)
        'light_brown': ([10, 50, 50], [30, 255, 255]),  # HSV range for light brown
        'dark_brown': ([0, 50, 50], [20, 255, 150]),  # HSV range for dark brown
        'blue_gray': ([90, 50, 50], [120, 255, 255]),  # HSV range for blue-gray
        'black': ([0, 0, 0], [180, 255, 30])  # HSV range for black
    }

    color_regions = {}
    present_colors = []

    for color_name, (lower, upper) in color_ranges.items():
        
        # Create mask using the color range
        lower = np.array(lower, dtype=np.uint8)
        upper = np.array(upper, dtype=np.uint8)
        color_mask = cv2.inRange(hsv_image, lower, upper)


        if color_mask.shape[:2] != mask.shape:
            mask = cv2.resize(mask, (color_mask.shape[1], color_mask.shape[0]), interpolation=cv2.INTER_NEAREST)

        # Apply provided mask
        masked_color_mask = cv2.bitwise_and(color_mask, mask)

        # Find contours in the masked color mask
        contours, _ = cv2.findContours(masked_color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter out small contours
        filtered_contours = [cnt for cnt in contours if cv2.contourArea(cnt) > 100]

        if len(filtered_contours) > 0:
            color_regions[color_name] = filtered_contours
            present_colors.append(color_name)

    colors_number = len(color_regions)
    if 'red' in present_colors and 'red2' in present_colors:
        colors_number -= 1
    
    return colors_number



def process_images(file_data, path_image, path_mask, feature_names):
    

    """
    Processes a set of images and their corresponding masks to extract predefined features. 

    Args:
        file_data (str): Path to the CSV file containing metadata about the images. 
        path_image (str): Base path where the image files are stored
        path_mask (str): Base path where the mask files are stored
        feature_names (list of str): List of the names of the features to be extracted from 
                                     each image-mask pair

    Returns:
        pd.DataFrame: A DataFrame where each row corresponds to an image-mask pair and each 
                      column to one of the specified features

    """
        
    # Where we will store the features
    file_features = 'features/features.xlsx'

    # Read meta-data into a Pandas dataframe
    df = pd.read_csv(file_data)

    # Extract image IDs and labels from the data.
    image_id = list(df['img_id'])
    mask_id = [id.replace('.png', '_mask.png') for id in df['img_id']]


    num_features = len(feature_names)
    features = []
    valid_image_ids = []

    # Loop through all images (limited by num_images)
    num_images = len(image_id)
    for i in np.arange(num_images):

        # Define filenames related to this image
        file_image = path_image + os.sep + image_id[i]
        file_image_mask = path_mask + os.sep + mask_id[i]

        # Check if both the image and mask files exist
        if exists(file_image) and exists(file_image_mask):
            # Read the image and mask
            im = cv2.imread(file_image)
            mask = cv2.imread(file_image_mask, cv2.IMREAD_GRAYSCALE)

            # Check if the mask has any contour other than just a black background
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if len(contours) == 0:
                # Skip this image if no contours are found in the mask
                continue
            
            # Measure features
            x = extract_features(im, mask)

            # Store in the list we created before
            features.append(x)

            # Keep track of the valid image ID
            valid_image_ids.append(image_id[i])

    # Create DataFrame from the features list and add image IDs
    df_features = pd.DataFrame(features, columns=feature_names)
    df_features['image_id'] = valid_image_ids
    return df_features

