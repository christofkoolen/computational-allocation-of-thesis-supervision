# -*- coding: utf-8 -*-
"""
Created on Tue Jun 24 00:57:44 2025

@author: chris

"""
#%%

# =============================================================================
# STEP 0: Update new names, email addresses, role, appointment, and profile_url manually
# =============================================================================

#%%

# =============================================================================
# STEP 1: Importing researcher profiles file
# =============================================================================

import pandas as pd

# Load the Excel file
researcher_profiles_2025_2026_df = pd.read_excel("researcher_profiles_2025_2026.xlsx")

# Check it's loaded
print(researcher_profiles_2025_2026_df.head())



#%%

# =============================================================================
# STEP 2A: scrape researchers' profile_description
# =============================================================================

import time
import requests
from bs4 import BeautifulSoup
import pandas as pd


# Create or overwrite the column
researcher_profiles_2025_2026_df['profile_description'] = None

for idx, url in enumerate(researcher_profiles_2025_2026_df['profile_url'], start=1):
    try:
        res = requests.get(url)
        res.raise_for_status()  # Raise error for bad responses
        soup = BeautifulSoup(res.text, 'html.parser')

        # Extract all text from <body>
        body = soup.find('body')
        full_text = body.get_text(separator=' ', strip=True) if body else 'N/A'

        # Assign directly to the dataframe
        researcher_profiles_2025_2026_df.at[idx - 1, 'profile_description'] = full_text

        print(f"✅ {idx}/{len(researcher_profiles_2025_2026_df)} Scraped: {url}")
        # time.sleep(0.5)  # Optional polite delay

    except Exception as e:
        print(f"❌ {idx}/{len(researcher_profiles_2025_2026_df)} Failed: {url} – {e}")
        researcher_profiles_2025_2026_df.at[idx - 1, 'profile_description'] = f"ERROR: {e}"
        
       
#%%
      
# =============================================================================
# STEP 2B: drop rows of researchers that have left
# =============================================================================


print(f"Initial rows before drop: {len(researcher_profiles_2025_2026_df)}")
# Drop rows where 'profile_description' contains the exact text "ERROR: 404 Client Error"
researcher_profiles_2025_2026_df = researcher_profiles_2025_2026_df[
    ~researcher_profiles_2025_2026_df['profile_description'].str.contains("ERROR: 404 Client Error", na=False)
].copy()

print(f" Remaining rows after drop: {len(researcher_profiles_2025_2026_df)}")

researcher_profiles_2025_2026_df_scraped = researcher_profiles_2025_2026_df

researcher_profiles_2025_2026_df.to_excel("researcher_profiles_2025_2026_interim.xlsx", index=False)
print("💾 Updated DataFrame saved.")

#%%


# =============================================================================
# STEP 3: Clean-up of the profile text
# =============================================================================

import re

# Define the unwanted header block (as plain string)
header_to_remove = (
    "KU Leuven Home CITIP Home About Board Members Staff Members "
    "Education Research Publications CiTiP Conferences Contact Home Staff members Staff Members "
)

# Define a cleaning function
def clean_profile_text(text):
    if not isinstance(text, str):
        return text  # skip NaN or non-string rows

    # Step 1: Remove the specific header
    cleaned = text.replace(header_to_remove, '')

    # Step 2: Start text *after* the first mention of "Contact"
    contact_index = cleaned.find("contact") #NOTE: this is case sensitive!!! Don't use Uppercase!
    if contact_index != -1:
        # Slice from the end of "Contact" onward
        cleaned = cleaned[contact_index + len("contact"):]

    # Step 3: Truncate everything below (and including) specific markers
    # Remove everything from "Publications query=user:" onward
    cleaned = re.split(r'Publications query=user:.*', cleaned)[0]

    # Remove everything from "Publications Type" onward
    cleaned = re.split(r'Publications Type.*', cleaned)[0]

    # Remove everything from "Publications Projects=user" onward
    cleaned = re.split(r'Publications Projects=user.*', cleaned)[0]

    return cleaned.strip()

# Overwrite the column directly
researcher_profiles_2025_2026_df['profile_description'] = (
    researcher_profiles_2025_2026_df['profile_description'].apply(clean_profile_text)
)



#%%


#%%

# =============================================================================
# STEP 4: Scrape and overwrite publication_list
# =============================================================================

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

# Step 1: Function to extract user ID from profile_url
def extract_user_id(profile_url):
    match = re.search(r'/staff/(\d+)$', str(profile_url))
    if match:
        numeric_id = match.group(1)
        # Drop the first character (one leading zero)
        return numeric_id[1:]
    return None

# Step 2: Function to scrape Lirias publication page
def get_publications(user_id):
    if not user_id:
        return "N/A"
    
    lirias_url = f"https://lirias.kuleuven.be/cv?Username=u{user_id}"
    
    try:
        response = requests.get(lirias_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract all visible text from the <body>
        body = soup.find('body')
        full_text = body.get_text(separator=' ', strip=True) if body else 'N/A'
        return full_text
    
    except Exception as e:
        print(f"❌ Failed for user {user_id}: {e}")
        return f"ERROR: {e}"

# Step 3: Overwrite publication_list in the main DataFrame
for idx, row in researcher_profiles_2025_2026_df.iterrows():
    user_id = extract_user_id(row['profile_url'])
    pub_text = get_publications(user_id)
    
    # Overwrite existing publication_list cell
    researcher_profiles_2025_2026_df.at[idx, 'publication_list'] = pub_text
    
    print(f"✅ {idx + 1}/{len(researcher_profiles_2025_2026_df)} Processed: u{user_id}")
    time.sleep(0.5)  # Polite delay to avoid overloading the server


#%%

# Optional: Save updated DataFrame
researcher_profiles_2025_2026_df.to_excel("researcher_profiles_2025_2026_updated.xlsx", index=False)
print("💾 Updated DataFrame saved.")


