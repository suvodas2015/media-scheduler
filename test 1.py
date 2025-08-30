import pandas as pd

csv_file = "recipients.csv"
df = pd.read_csv(csv_file, dtype=str)

def clean_number(num):
    try:
        # Convert scientific notation string to int, then back to string
        return str(int(float(num)))
    except:
        return str(num).strip()

df['mobile_number'] = df['mobile_number'].apply(clean_number)

print("✅ Cleaned numbers:")
print(df['mobile_number'])
