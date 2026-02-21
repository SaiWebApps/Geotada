# Troubleshooting Guide

## Fixed: "object object" Error

### Problem
When trying to register a user, you were seeing an error message that said "object object" instead of a readable error message.

### Cause
FastAPI returns validation errors as an array of objects, not a simple string. The JavaScript code was trying to display this array directly, which resulted in "[object Object]" being shown.

### Solution
Updated the HTML form to include a `formatErrorMessage()` function that properly handles:
- String error messages (simple errors)
- Array error messages (validation errors)
- Object error messages (complex errors)

### How to Test the Fix

1. **Refresh the page**: Hard refresh the HTML form in your browser (Cmd+Shift+R or Ctrl+Shift+F5)

2. **Try these test scenarios**:

   **Scenario 1: Missing required field**
   - Leave the email field empty
   - Try to submit
   - Should see: "body.email: field required"

   **Scenario 2: Invalid email format**
   - Enter "notanemail" in the email field
   - Try to submit
   - Should see: "body.email: value is not a valid email address"

   **Scenario 3: Weak password**
   - Use password: "weak"
   - Should see error about password requirements

   **Scenario 4: Successful registration**
   - Fill in all fields correctly:
     - Email: youremail@example.com
     - Username: yourusername (must be unique)
     - Password: SecurePass123
     - First Name: Your Name
     - Last Name: Last Name
     - Select some interests by clicking the tags
   - Submit
   - Should see success message and user info displayed

## Common Issues and Solutions

### Issue 1: "Error connecting to server"

**Symptoms**: Cannot connect to the API at all

**Solutions**:
```bash
# Check if backend is running
curl http://localhost:8000/health

# If not running, start it:
cd /Users/adamserblowski/Geotada/backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Issue 2: "Email already registered"

**Symptoms**: You've already registered with this email

**Solutions**:
- Use a different email address
- Or delete the existing user from the database:
  ```bash
  cd /Users/adamserblowski/Geotada/backend
  rm geotada.db
  alembic upgrade head  # Recreate database
  ```

### Issue 3: "Username already taken"

**Symptoms**: Username is not unique

**Solution**: Choose a different username

### Issue 4: Password validation errors

**Symptoms**:
- "Password must be at least 8 characters long"
- "Password must contain at least one digit"
- "Password must contain at least one uppercase letter"
- "Password must contain at least one lowercase letter"

**Solution**: Use a password that meets all requirements:
- At least 8 characters
- Contains uppercase letter (A-Z)
- Contains lowercase letter (a-z)
- Contains number (0-9)

Example valid passwords:
- `SecurePass123`
- `MyPassword1`
- `Travel2024App`

### Issue 5: Form not submitting

**Symptoms**: Click submit but nothing happens

**Solutions**:
1. Check browser console for errors (F12 → Console tab)
2. Make sure JavaScript is enabled
3. Hard refresh the page (Cmd+Shift+R)
4. Check that backend is running on http://localhost:8000

### Issue 6: Interests not saving

**Symptoms**: Interests don't show up after registration

**Solution**: Click the interest tags BEFORE submitting the form. Selected tags should turn purple.

## Testing the Registration Flow

### Step-by-Step Test

1. **Open the form**:
   - File should be open in your browser
   - If not: `open /Users/adamserblowski/Geotada/frontend-demo/index.html`

2. **Verify backend is running**:
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status":"healthy"}
   ```

3. **Fill in the registration form**:
   - Email: `test@example.com`
   - Username: `testuser123`
   - Password: `TestPass123`
   - First Name: `Test`
   - Last Name: `User`
   - Phone: `+1234567890`
   - Click interest tags: History, Art, Food

4. **Submit the form**

5. **Verify success**:
   - Should see green success message
   - User info should display below the form
   - Access token should be visible

6. **Test login**:
   - Switch to "Login" tab
   - Email: `test@example.com`
   - Password: `TestPass123`
   - Submit
   - Should see success message with updated last_login time

## Debugging Tips

### View API Response in Browser Console

1. Open browser console (F12)
2. Go to Network tab
3. Submit the form
4. Click on the "register" request
5. View the Response tab to see the exact error from the API

### Test API Directly

```bash
# Test registration with curl
curl -X POST http://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test2@example.com",
    "username": "testuser2",
    "password": "TestPass123",
    "first_name": "Test",
    "last_name": "User"
  }'
```

### Check Backend Logs

The backend server running in your terminal will show logs:
- Request received
- Validation errors
- Database operations
- Response sent

### Reset Database

If you need to start fresh:

```bash
cd /Users/adamserblowski/Geotada/backend

# Stop the server (Ctrl+C if running in foreground)

# Delete database
rm geotada.db

# Recreate tables
source venv/bin/activate
alembic upgrade head

# Restart server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Error Message Reference

| Error Message | Meaning | Solution |
|--------------|---------|----------|
| `field required` | Required field is missing | Fill in the field |
| `value is not a valid email address` | Email format is invalid | Use proper email format |
| `String should have at least X characters` | Input too short | Add more characters |
| `Email already registered` | Email is already in use | Use different email |
| `Username already taken` | Username is already in use | Choose different username |
| `Password must be at least 8 characters long` | Password too short | Use 8+ character password |
| `Password must contain at least one digit` | No number in password | Add a number (0-9) |
| `Password must contain at least one uppercase letter` | No uppercase letter | Add uppercase letter (A-Z) |
| `Password must contain at least one lowercase letter` | No lowercase letter | Add lowercase letter (a-z) |
| `Incorrect email or password` | Login credentials wrong | Check email and password |
| `User account is inactive` | Account was deactivated | Contact admin or reactivate |

## Still Having Issues?

If you're still experiencing problems:

1. **Check all prerequisites**:
   - Backend running: `curl http://localhost:8000/health`
   - Python venv activated
   - Database exists: `ls backend/geotada.db`

2. **Review the logs**:
   - Backend terminal output
   - Browser console (F12)

3. **Try the API directly** using curl commands in [DEMO_RESULTS.md](DEMO_RESULTS.md)

4. **Run the tests**:
   ```bash
   cd backend
   source venv/bin/activate
   pytest -v
   ```
   All 24 tests should pass.

5. **Check the documentation**:
   - [README.md](README.md) - Full project documentation
   - [DEMO_RESULTS.md](DEMO_RESULTS.md) - API examples
   - [NEXT_STEPS.md](NEXT_STEPS.md) - Mobile app setup
