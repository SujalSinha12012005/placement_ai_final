import csv

# Create users.csv with header if it doesn't exist or you want to reset
with open('users.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Email', 'Password'])  # Header row

# Add a test user (you can add more later via signup)
with open('users.csv', 'a', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['test@gmail.com', '123456'])
