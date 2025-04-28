# Glasir Timetable API

## Purpose

This API provides endpoints to extract and retrieve timetable data from the Glasir online system.

## Setup

It is recommended to use a virtual environment.

1.  **Create a virtual environment (optional):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r glasir_api/requirements.txt
    ```

## Running the API

To start the API server, run the following command from the project's root directory (`V0.3`):

```bash
uvicorn glasir_api.main:app --host 0.0.0.0 --port 8000
```

For development, you can use the `--reload` flag to automatically restart the server when code changes are detected:

```bash
uvicorn glasir_api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Authentication Helper

The `get_glasir_auth.py` script, located in the parent directory (`V0.3`), helps obtain the necessary authentication details (`Cookie` header and `student_id`) required by the API endpoints.

Run the script using:

```bash
python ../get_glasir_auth.py --force-login
```

This will prompt you for your Glasir username and password and save the required `Cookie` string and `student_id` to files (`glasir_auth_tool/cookies.json` and `glasir_auth_tool/student_id.txt` respectively) in the `glasir_auth_tool` directory. You will need these values for the API requests.

## API Endpoints

The following endpoints are available:

### Get Timetable for a Specific Week Offset

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/{offset}`
*   **Path Parameters:**
    *   `username`: Your Glasir username (e.g., `rm3112z9`).
    *   `offset`: The week offset relative to the current week (e.g., `0` for the current week, `-1` for the previous week, `1` for the next week).
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string obtained from `get_glasir_auth.py`.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/0?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON object representing the `TimetableData` for the specified week.

### Get Timetable for All Available Weeks

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/all`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/all?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects for all weeks found.

### Get Timetable from Current Week Forward

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/current_forward`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/current_forward?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects starting from the current week.

### Get Timetable for a Specific Number of Weeks Forward

*   **Method:** `GET`
*   **Path:** `/profiles/{username}/weeks/forward/{count}`
*   **Path Parameters:**
    *   `username`: Your Glasir username.
    *   `count`: The number of weeks forward from the current week to retrieve (inclusive of the current week).
*   **Query Parameters:**
    *   `student_id`: Your Glasir student ID.
*   **Required Headers:**
    *   `Cookie`: The authentication cookie string.
*   **Example `curl`:**
    ```bash
    curl -X GET -H "Cookie: YOUR_COOKIE_STRING" "http://localhost:8000/profiles/YOUR_USERNAME/weeks/forward/5?student_id=YOUR_STUDENT_ID"
    ```
*   **Response:** A JSON array containing `TimetableData` objects for the specified number of weeks forward.