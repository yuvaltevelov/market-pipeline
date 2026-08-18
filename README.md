# Market Pipeline

דשבורד שוק אישי, מותאם למובייל ול-RTL.

## פרסום ב-GitHub Pages

1. GitHub repository → **Settings** → **Pages**.
2. תחת **Build and deployment**, בחר **Deploy from a branch**.
3. בחר branch: `main`, folder: `/(root)`, ואז Save.
4. לאחר הפרסום: `https://yuvaltevelov.github.io/market-pipeline/`.

## עדכון

- כפתור **עדכן נתונים** באתר מוביל ל-GitHub Actions. לחץ **Run workflow** כאשר מחובר ל-GitHub.
- GitHub Action חינמי מעדכן כרגע רק סמן זמן לפי לוח זמנים.
- כדי למשוך מחירים וחדשות אמיתיים באופן אוטונומי יש להוסיף ספק נתונים/API ולשמור מפתחות רק ב-GitHub Secrets. לעולם לא להכניס מפתחות ל-`index.html` או ל-`data/latest.json`.

## פרטיות

המאגר ציבורי, לכן אל תכניס סודות, API keys או פרטי ברוקר. נתוני התיק שנמצאים ב-JSON גלויים לציבור.
