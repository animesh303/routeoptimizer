import json

# import requests
import pandas as pd

# from botocore.vendored import requests
import requests

# from tabulate import tabulate
# import sys
from itertools import permutations
import re
from datetime import datetime, timedelta
import os
import boto3

# Provide API Key
# api_key = "AIzaSyCvkCRGxQqk1LfqhXbTH6kHMnTqZkhfj5w"
api_key_name = os.environ.get("google_api_key")
lunch_duration_mins = int(os.environ.get("lunch_duration_mins"))
dinner_duration_mins = int(os.environ.get("dinner_duration_mins"))
lunch_hr = int(os.environ.get("lunch_hr"))
dinner_hr = int(os.environ.get("dinner_hr"))


# lunch_duration_mins = 60
# dinner_duration_mins = 60
# lunch_hr = 12
# dinner_hr = 19
tour_start_datetime = datetime(2023, 12, 23, 9, 0, 0)
date_format = "%I:%M %p, %a, %d-%b-%Y"
assignment_bucket_name = os.environ.get("assignment_bucket")


def lambda_handler(event, context):
    s3 = boto3.client("s3")
    ssm_client = boto3.client("ssm")

    # s3_object_attractions = s3.get_object(
    #     Bucket=assignment_bucket_name, Key="attractions.xlsx"
    # )
    # attractions_content = s3_object_attractions["Body"].read()
    # attractions_file = BytesIO(attractions_content)

    # Retrieve the secret value from Parameter Store
    try:
        response = ssm_client.get_parameter(
            Name=api_key_name,
            WithDecryption=True,  # Specify WithDecryption=True to decrypt SecureString parameters
        )
        google_api_key = response["Parameter"]["Value"]

        # Use the secret value as needed
        # print(f"Retrieved secret name: {google_api_key}")

    except ssm_client.exceptions.ParameterNotFound:
        print(f"Parameter '{api_key_name}' not found.")

    except Exception as e:
        print(f"Error retrieving secret: {e}")

    print("Downloading attactions file...")

    s3.download_file(
        assignment_bucket_name, "attractions.xlsx", "/tmp/attractions.xlsx"
    )

    attractions_file = "/tmp/attractions.xlsx"

    # attractions_file = "attractions.xlsx"
    distance_file = "/tmp/distance.xlsx"
    plan_file = "/tmp/metrics.xlsx"
    plan_file_inc_metrics = "/tmp/TripPlan-metrics.xlsx"
    plan_file_final = "/tmp/TripPlan-Final.xlsx"
    plan_html = "/tmp/TripPlan.html"

    # cleanup()

    # df = pd.read_excel (attractions_file)

    print("Generating distance file...")

    generate_distance_file(attractions_file, distance_file, google_api_key)

    unique_cities, city_to_index = generate_city_to_index(distance_file)
    distance_matrix = generate_distance_matrix(
        distance_file, unique_cities, city_to_index
    )

    # Replace `start_city` with the index of your fixed starting city.

    print("Obtaining start city...")
    start_city = get_origin_index(attractions_file, city_to_index)

    print("Generating best route ...")
    best_route, min_distance = traveling_salesman_bruteforce_fixed_start(
        distance_matrix, start_city
    )

    #     best_route, min_distance = traveling_salesman_bruteforce(distance_matrix)

    # Convert numerical indices back to city names
    index_to_city = {index: city for city, index in city_to_index.items()}
    best_route_cities = [index_to_city[index] for index in best_route]

    # Ensure that the last city is the starting city
    best_route_cities.append(index_to_city[start_city])

    df_output = pd.DataFrame(
        {
            "From": best_route_cities[
                :-1
            ],  # Exclude the last city since it's the return to the starting city
            "To": best_route_cities[
                1:
            ],  # Exclude the first city since it's the starting city
        }
    )

    print("Merging plan with metrics ...")

    merged_plan_df = merge_plan_with_metrics(df_output, distance_file, attractions_file)
    # print (merged_plan_df)

    # df_output.to_excel(plan_file, index=False)
    merged_plan_df.to_excel(plan_file, index=False)

    print("Adding timings to plan ...")

    add_plan_timings(plan_file, plan_file_inc_metrics)
    # adjust_meal(plan_file_final)

    print("Including lunch and dinner ...")
    include_meals(plan_file_inc_metrics, plan_file_final)
    print("Generating HTML report ...")
    generate_html_report(plan_file_final, plan_html)

    print(f"Best route written to '{plan_file_final}' and '{plan_html}'.")

    s3.upload_file(
        plan_file_final,
        assignment_bucket_name,
        f"TripPlan-{tour_start_datetime.strftime('%Y%m%d')}.xlsx",
    )

    s3.upload_file(
        plan_file_inc_metrics,
        assignment_bucket_name,
        f"TripPlan-metrics-{tour_start_datetime.strftime('%Y%m%d')}.xlsx",
    )

    return {"statusCode": 200, "body": json.dumps("Successfull!")}


def get_dist_dur(api_key, start, end):
    base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "traffic_model": "optimistic",
        "departure_time": "now",
        "origins": start,
        "destinations": end,
        "key": api_key,
    }

    print("Origin: ", start, " Destination: ", end)

    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "OK":
            try:
                distance = data["rows"][0]["elements"][0]["distance"]["text"]
                duration = data["rows"][0]["elements"][0]["duration"]["text"]

                print("Distance: ", distance, " Duration: ", duration)
                return distance, duration
            except Exception as e:
                print("Exception:", e, ". Check Google Map for address ", end)
                return 0, 0
        else:
            print("Request failed.")
            return None, None
    else:
        print("Failed to make the request.")
        return None, None


def convert_to_minutes(time_string):
    # Use regular expression to extract hours and minutes
    # match = re.match(r'(\d+)\s*hour(?:s)?\s*(\d+)?\s*min(?:ute)?(?:s)?', time_string)
    match = re.match(
        r"(?:(\d+)\s*hour(?:s)?)?\s*(?:(\d+) ?min(?:ute)?(?:s)?)?", time_string
    )

    # print('Time string received:', time_string)

    if match:
        # print('Matched regular expression')
        # Extract hours and minutes
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0

        # Convert to total minutes
        total_minutes = hours * 60 + minutes
        return total_minutes
    else:
        return None  # Return None for invalid input


def generate_distance_file(attractions_file, distance_file, google_api_key):
    # Read the Excel file and extract the "attractions" column
    df = pd.read_excel(attractions_file)
    attractions_column = df["Attractions"]

    print("Generating permutations from the attractions column ...")
    attractions_permutations = permutations(attractions_column, 2)
    # Create a DataFrame for the permutations
    permutations_df = pd.DataFrame(
        attractions_permutations, columns=["source", "destination"]
    )

    # Using iterrows() to iterate over rows
    for index, row in permutations_df.iterrows():
        # print(f"Index: {index}, Name: {row['Name']}, Age: {row['Age']}, City: {row['City']}")
        source = row["source"]
        destination = row["destination"]
        distance, duration = get_dist_dur(google_api_key, source, destination)
        duration = convert_to_minutes(duration)
        distance = re.sub(r"\b\d+\s*m\b", "0", distance)
        distance = distance.replace(" km", "")
        distance = float(distance)
        permutations_df.at[index, "distance_kms"] = distance
        permutations_df.at[index, "duration_mins"] = duration

    # Write the DataFrame to a new Excel file
    permutations_df.to_excel(distance_file, index=False)

    # print('Distance file generated!')


def calculate_total_distance(route, distances):
    total_distance = 0
    for i in range(len(route) - 1):
        total_distance += distances[route[i]][route[i + 1]]
    total_distance += distances[route[-1]][route[0]]  # Return to the starting city
    return total_distance


def traveling_salesman_bruteforce_fixed_start(distances, start_city):
    num_cities = len(distances)
    all_cities = set(range(num_cities))

    # Exclude the starting city from permutations
    remaining_cities = list(all_cities - {start_city})

    # Generate all possible routes for the remaining cities
    all_routes = permutations(remaining_cities)

    min_distance = float("inf")
    best_route = None

    for route in all_routes:
        # Insert the starting city at the beginning of the route
        current_route = (start_city,) + route
        distance = calculate_total_distance(current_route, distances)
        if distance < min_distance:
            min_distance = distance
            best_route = current_route

    return best_route, min_distance


def generate_city_to_index(distance_file):
    # Read the Excel file
    df = pd.read_excel(distance_file)

    # Map string labels to numerical indices
    unique_cities = set(df["source"].tolist() + df["destination"].tolist())
    city_to_index = {city: index for index, city in enumerate(unique_cities)}

    #     print ('unique_cities: ', unique_cities)
    #     print ('city_to_index: ', city_to_index)

    return unique_cities, city_to_index


def generate_distance_matrix(distance_matrix_file, unique_cities, city_to_index):
    # Read the Excel file
    df = pd.read_excel(distance_matrix_file)

    # Replace string labels with numerical indices
    df["source_index"] = df["source"].map(city_to_index)
    df["destination_index"] = df["destination"].map(city_to_index)

    # Create a distance matrix
    num_cities = len(unique_cities)
    distance_matrix = [[float("inf")] * num_cities for _ in range(num_cities)]

    for _, row in df.iterrows():
        source_index = row["source_index"]
        dest_index = row["destination_index"]
        distance = row["distance_kms"]
        distance_matrix[source_index][dest_index] = distance
        distance_matrix[dest_index][
            source_index
        ] = distance  # Assuming it's an undirected graph

    return distance_matrix


def get_origin_index(attractions_file, city_to_index):
    df = pd.read_excel(attractions_file)
    origin_city = df.loc[0, "Attractions"]
    # Find the index of the specific city using the city_to_index dictionary
    origin_index = city_to_index.get(origin_city)
    return origin_index


def merge_plan_with_metrics(plan_df, distance_file, attractions_file):
    df_attractions = pd.read_excel(attractions_file)
    df_distance = pd.read_excel(distance_file)

    # print(plan_df)
    # print(df_distance)

    print("Merging plan with metrics")
    # Merge DataFrames based on "source" and "destination" columns
    # df_merged = pd.merge(plan_df, df_distance, on=['source', 'destination'], how='left')

    merged_df_phase_1 = pd.merge(
        plan_df,
        df_distance,
        right_on=["source", "destination"],
        left_on=["From", "To"],
        how="inner",
    )
    merged_df_phase_2 = pd.merge(
        merged_df_phase_1,
        df_attractions,
        right_on=["Attractions"],
        left_on=["destination"],
        how="inner",
    )

    merged_df = merged_df_phase_2.drop(["source", "destination", "Attractions"], axis=1)

    merged_df = merged_df.rename(columns={"distance_kms": "Distance(Kms)"})
    merged_df = merged_df.rename(columns={"duration_mins": "Duration(Mins)"})
    return merged_df


def add_plan_timings(plan_file, plan_file_final):
    # Set a fixed start time (e.g., 9:00 AM)
    # fixed_start_time = pd.to_datetime('09:00:00')
    fixed_start_time = tour_start_datetime

    # Assuming you have a DataFrame 'df' with columns 'attractions' and 'Leisure Time (Mins)'
    # Replace 'your_excel_file.xlsx' with your actual file name
    df = pd.read_excel(plan_file)

    # Assuming the 'Leisure Time (Mins)' column is in minutes
    # If it's in another time unit (e.g., hours), adjust the multiplier accordingly

    # Convert 'Leisure Time (Mins)' to timedelta
    df["Leisure Time (Mins)"] = pd.to_timedelta(df["Leisure Time (Mins)"], unit="m")
    df["Duration(Mins)"] = pd.to_timedelta(df["Duration(Mins)"], unit="m")

    # Calculate consecutive start time and end time
    df["Start Time"] = (
        fixed_start_time
        + df["Leisure Time (Mins)"].cumsum()
        - df["Leisure Time (Mins)"]
        + df["Duration(Mins)"].cumsum()
    )
    df["End Time"] = df["Start Time"] + df["Leisure Time (Mins)"]

    # Add x minutes to start time if it's greater than 12 PM
    # Adjust the value as needed
    # df.loc[df['Start Time'].dt.hour > 12, ['Start Time', 'End Time']] += pd.to_timedelta(lunch_duration_mins, unit='m')
    df["Start Time"] = df.apply(
        lambda row: row["Start Time"] + pd.Timedelta(minutes=lunch_duration_mins)
        if row["Start Time"].hour >= 12
        else row["Start Time"],
        axis=1,
    )
    df["End Time"] = df.apply(
        lambda row: row["End Time"] + pd.Timedelta(minutes=lunch_duration_mins)
        if row["Start Time"].hour >= 12
        else row["End Time"],
        axis=1,
    )

    df["Start Time"] = df.apply(
        lambda row: row["Start Time"] + pd.Timedelta(minutes=dinner_duration_mins)
        if row["Start Time"].hour >= 19
        else row["Start Time"],
        axis=1,
    )
    df["End Time"] = df.apply(
        lambda row: row["End Time"] + pd.Timedelta(minutes=dinner_duration_mins)
        if row["Start Time"].hour >= 19
        else row["End Time"],
        axis=1,
    )

    df["Leisure Time (Mins)"] = df["Leisure Time (Mins)"].dt.total_seconds() / 60
    df["Duration(Mins)"] = df["Duration(Mins)"].dt.total_seconds() / 60

    df["Start Time"] = df["Start Time"].dt.strftime(date_format)
    df["End Time"] = df["End Time"].dt.strftime(date_format)

    # Save the DataFrame back to Excel or perform other operations as needed
    # Replace 'output_file.xlsx' with your desired output file name
    df.to_excel(plan_file_final, index=False)


# def cleanup():
#     # Replace the list with the actual file names you want to delete
#     files_to_delete = [
#         # 'distance.xlsx',
#         "metrics.xlsx",
#         # 'TripPlan.xlsx',
#         # 'plan_with_meal.xlsx'
#     ]

#     for file_to_delete in files_to_delete:
#         # Check if the file exists before attempting to delete
#         if os.path.exists(file_to_delete):
#             os.remove(file_to_delete)
#             print(f"{file_to_delete} has been deleted.")
#         else:
#             print(f"{file_to_delete} does not exist.")


# Function to check if the time is greater than 12 pm
def is_after_lunchtime(time_value):
    return time_value.hour >= lunch_hr


def is_after_dinnertime(time_value):
    return time_value.hour >= dinner_hr  # 19 represents 7 pm in 24-hour format


def include_meals(plan_file_inc_metrics, plan_file_final):
    df_metric = pd.read_excel(plan_file_inc_metrics)
    # df_metric_original = df_metric
    df_metric["Original End Time"] = df_metric["End Time"]

    # Convert the "End Time" column to datetime format
    df_metric["End Time"] = pd.to_datetime(
        df_metric["End Time"], format="%I:%M %p, %a, %d-%b-%Y"
    )

    # Iterate through the DataFrame and insert a row after if the time is greater than 12 pm
    lunch_row = []
    for index, row in df_metric.iterrows():
        if is_after_lunchtime(row["End Time"]):
            print("after lunch ", row["End Time"])
            # Insert a row with the same values as the current row
            lunch_start = row["End Time"] + timedelta(minutes=1)
            lunch_end = lunch_start + timedelta(minutes=lunch_duration_mins)
            # lunch_row.append(index + 0.5)
            lunch_row.append(
                {
                    "From": "Lunch",
                    "To": "Lunch",
                    "Distance(Kms)": 0,
                    "Duration(Mins)": 0,
                    "Leisure Time (Mins)": 60,
                    "Start Time": lunch_start.strftime("%I:%M %p, %a, %d-%b-%Y"),
                    "Original End Time": lunch_end.strftime("%I:%M %p, %a, %d-%b-%Y"),
                }
            )

            break

    df_metric = pd.concat(
        [
            df_metric.iloc[: int(index + 1)],
            pd.DataFrame(lunch_row, columns=df_metric.columns),
            df_metric.iloc[int(index + 1) :],  # noqa
        ]
    ).reset_index(drop=True)

    # Iterate through the DataFrame and insert a row after if the time is greater than 12 pm
    dinner_row = []
    for index, row in df_metric.iterrows():
        if is_after_dinnertime(row["End Time"]):
            print("after dinner ", row["End Time"])
            # Insert a row with the same values as the current row
            dinner_start = row["End Time"] + timedelta(minutes=1)
            dinner_end = dinner_start + timedelta(minutes=dinner_duration_mins)
            # lunch_row.append(index + 0.5)
            dinner_row.append(
                {
                    "From": "Dinner",
                    "To": "Dinner",
                    "Distance(Kms)": 0,
                    "Duration(Mins)": 0,
                    "Leisure Time (Mins)": 60,
                    "Start Time": dinner_start.strftime("%I:%M %p, %a, %d-%b-%Y"),
                    "Original End Time": dinner_end.strftime("%I:%M %p, %a, %d-%b-%Y"),
                }
            )
            break
    df_metric = pd.concat(
        [
            df_metric.iloc[: int(index + 1)],
            pd.DataFrame(dinner_row, columns=df_metric.columns),
            df_metric.iloc[int(index + 1) :],  # noqa
        ]
    ).reset_index(drop=True)

    df_metric["End Time"] = df_metric["Original End Time"]
    df_metric = df_metric.drop(columns=["Original End Time"])

    df_metric.to_excel(plan_file_final, index=False)


def generate_html_report(plan_file_final, plan_html):
    df = pd.read_excel(plan_file_final)
    # Convert DataFrame to HTML
    html_output = df.to_html(index=False)

    # Write HTML to a file
    with open(plan_html, "w") as file:
        file.write(html_output)
