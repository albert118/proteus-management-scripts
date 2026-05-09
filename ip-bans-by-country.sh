#!/bin/bash
source .env

# Name of the file containing IP addresses (one per line)
FILE="ip_list.txt"

# Files for storing counts
COUNTRY_FILE="country_count.txt"
ORG_FILE="org_count.txt"
CITY_FILE="city_count.txt"

# Initialize counting files if they do not exist
> "$COUNTRY_FILE"
> "$ORG_FILE"
> "$CITY_FILE"


# Check we can access IP Info and can reach them
preflight() {
  echo "Beginning preflight"
  if curl --fail -H "Authorization: Bearer ${IPINFO_API_KEY}" "https://api.ipinfo.io/lite/8.8.8.8"; then
    echo "Preflight valid, continuing"
  else
    echo "Cannot access IP Info API. Check the environment and network."
    exit 1
  fi
}

# Function to obtain geolocation information of an IP address
get_ip_info() {
  local ip=$1
  curl -H "Authorization: Bearer ${IPINFO_API_KEY}" \
       -s "https://ipinfo.io/$ip?token=$IPINFO_API_KEY"
}

# Check if the file exists
if [ ! -f "$FILE" ]; then
  echo "File $FILE not found."
  exit 1
fi

preflight

# Iterate over each line in the file
while IFS= read -r ip
do
  echo "Processing ${ip}..."
  ip_info=$(get_ip_info "$ip")
  country=$(echo "$ip_info" | jq -r '.country')
  org=$(echo "$ip_info" | jq -r '.org')
  city=$(echo "$ip_info" | jq -r '.city')
  
  # Update counting files
  echo "$country" >> "$COUNTRY_FILE"
  echo "$org" >> "$ORG_FILE"
  echo "$city" >> "$CITY_FILE"
done < "$FILE"

# Function to count occurrences
count_occurrences() {
  sort -bfg | uniq -c
}

# Function to sort occurrences
sort_occurrences() {
  sort -rn -k1,1
}

# Display statistics
echo "Statistics by country code:"
cat "$COUNTRY_FILE" | count_occurrences | sort_occurrences

echo "Statistics by organization:"
cat "$ORG_FILE" | count_occurrences | sort_occurrences

echo "Statistics by city:"
cat "$CITY_FILE" | count_occurrences | sort_occurrences