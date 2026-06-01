import sqlite3

conn = sqlite3.connect("src/database/products.db")
cursor = conn.cursor()

cursor.execute("SELECT DISTINCT inch FROM products LIMIT 10")
print([row[0] for row in cursor.fetchall()])

conn.close()