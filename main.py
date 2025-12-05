import psycopg2
import tkinter as tk
from tkinter import ttk, messagebox
import hashlib

# ПОДКЛЮЧЕНИЕ К БАЗЕ

def get_connection():
    return psycopg2.connect(
        dbname="project db",
        user="postgres",
        password="1234",
        host="localhost",
        port="5432"
    )

# USERS + LOGS + AUTOCREATE TABLES

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(200) NOT NULL,
            role VARCHAR(20) DEFAULT 'user',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(username, password, role='user'):
    conn = get_connection()
    cur = conn.cursor()

    password_hash = hash_password(password)

    cur.execute("""
        INSERT INTO users (username, password_hash, role)
        VALUES (%s, %s, %s)
        ON CONFLICT (username) DO NOTHING
    """, (username, password_hash, role))

    conn.commit()
    cur.close()
    conn.close()


def login(username, password):
    conn = get_connection()
    cur = conn.cursor()

    password_hash = hash_password(password)

    cur.execute("""
        SELECT id, role FROM users 
        WHERE username = %s AND password_hash = %s
    """, (username, password_hash))

    user = cur.fetchone()

    cur.close()
    conn.close()
    return user


def add_log(user_id, action, details=None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO logs (user_id, action, details)
        VALUES (%s, %s, %s)
    """, (user_id, action, details))

    conn.commit()
    cur.close()
    conn.close()


def ensure_admin():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE username = %s", ('admin',))
    user = cur.fetchone()

    if not user:
        create_user("admin", "admin123", "admin")
        print("Создан администратор: admin / admin123")

        cur.execute("SELECT id FROM users WHERE username = %s", ('admin',))
        user = cur.fetchone()

    cur.close()
    conn.close()
    return user[0]


init_db()
CURRENT_USER_ID = ensure_admin()

# CATEGORIES 

def get_categories():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM categories ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def refresh_categories():
    global categories_list, category_names
    categories_list = get_categories()
    category_names = [r[1] for r in categories_list]
    try:
        combobox_category['values'] = category_names
    except:
        pass


# MATERIALS 

def load_materials():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.name, m.unit, m.quantity, COALESCE(c.name, '')
        FROM materials m
        LEFT JOIN categories c ON m.category_id = c.id
        ORDER BY m.id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def add_category(name):
    if not name.strip():
        raise ValueError("Имя категории не может быть пустым")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", (name,))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return new_id


def add_material(name, unit, quantity, min_quantity, category_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO materials (name, unit, quantity, min_quantity, category_id)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
    """, (name, unit, quantity, min_quantity, category_id))

    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return new_id

# ОПЕРАЦИИ (ПРИХОД/РАСХОД)

def increase_material(user_id, material_id, amount):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE materials 
        SET quantity = quantity + %s
        WHERE id = %s
    """, (amount, material_id))

    cur.execute("""
        INSERT INTO transactions (material_id, type, amount, comment)
        VALUES (%s, 'приход', %s, 'Операция через программу')
    """, (material_id, amount))

    add_log(user_id, "Приход", f"ID={material_id}, amount={amount}")

    conn.commit()
    cur.close()
    conn.close()


def decrease_material(user_id, material_id, amount):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT quantity FROM materials WHERE id = %s", (material_id,))
    res = cur.fetchone()

    if not res:
        raise ValueError("Материал не найден")

    if res[0] < amount:
        raise ValueError("Недостаточно материалов")

    cur.execute("""
        UPDATE materials
        SET quantity = quantity - %s
        WHERE id = %s
    """, (amount, material_id))

    cur.execute("""
        INSERT INTO transactions (material_id, type, amount, comment)
        VALUES (%s, 'расход', %s, 'Операция через программу')
    """, (material_id, amount))

    add_log(user_id, "Расход", f"ID={material_id}, amount={amount}")

    conn.commit()
    cur.close()
    conn.close()


def load_transactions():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, COALESCE(m.name, ''), t.type, t.amount, t.comment, t.operation_date
        FROM transactions t
        LEFT JOIN materials m ON t.material_id = m.id
        ORDER BY t.id DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows



# УДАЛЕНИЕ МАТЕРИАЛОВ 

def delete_material(material_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT name FROM materials WHERE id = %s", (material_id,))
    res = cur.fetchone()
    material_name = res[0] if res else "Unknown"
 
    cur.execute("DELETE FROM transactions WHERE material_id = %s", (material_id,))


    cur.execute("DELETE FROM materials WHERE id = %s", (material_id,))

    add_log(CURRENT_USER_ID, "Удаление материала", f"{material_name} (ID={material_id})")

    conn.commit()
    cur.close()
    conn.close()



def delete_material_window():
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("Внимание", "Выберите материал в таблице")
        return

    item = tree.item(selected[0])
    material_id = item["values"][0]
    material_name = item["values"][1]

    answer = messagebox.askyesno("Подтверждение",
                                 f"Удалить материал '{material_name}' (ID={material_id})?")
    if not answer:
        return

    delete_material(material_id)
    refresh_table()
    messagebox.showinfo("Успех", "Материал удалён")



# УДАЛЕНИЕ КАТЕГОРИЙ 

def delete_category(category_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM materials WHERE category_id = %s", (category_id,))
    count = cur.fetchone()[0]

    if count > 0:
        messagebox.showerror("Ошибка", "В категории есть материалы. Удаление невозможно.")
        cur.close()
        conn.close()
        return

    cur.execute("SELECT name FROM categories WHERE id = %s", (category_id,))
    res = cur.fetchone()
    category_name = res[0] if res else "Unknown"

    cur.execute("DELETE FROM categories WHERE id = %s", (category_id,))

    add_log(CURRENT_USER_ID, "Удаление категории", category_name)

    conn.commit()
    cur.close()
    conn.close()

    refresh_categories()
    refresh_table()



def delete_category_window():
    if not category_names:
        messagebox.showinfo("Ошибка", "Нет категорий.")
        return

    win = tk.Toplevel(root)
    win.title("Удаление категории")
    win.geometry("300x150")

    ttk.Label(win, text="Выберите категорию:").pack(pady=10)

    combo = ttk.Combobox(win, values=category_names, state="readonly")
    combo.pack()

    if category_names:
        combo.current(0)

    def delete_selected():
        cat_name = combo.get()
        category_id = next(cid for cid, cname in categories_list if cname == cat_name)

        answer = messagebox.askyesno("Подтверждение",
                                     f"Удалить категорию '{cat_name}'?")
        if not answer:
            return

        delete_category(category_id)
        win.destroy()

    ttk.Button(win, text="Удалить", command=delete_selected).pack(pady=10)



#ДИЗАЙН

def apply_style(root):
    style = ttk.Style()
    style.theme_use("default")

    style.configure("TButton", font=("Segoe UI", 10), padding=6, background="#e6e6e6")
    style.map("TButton", background=[("active", "#d0d0d0")])

    style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    style.configure("TFrame", background="#f5f5f5")
    style.configure("TLabel", background="#f5f5f5")

    root.configure(bg="#f5f5f5")

#  GUI

def refresh_table():
    for row in tree.get_children():
        tree.delete(row)
    for row in load_materials():
        tree.insert("", tk.END, values=row)


def add_category_window():
    win = tk.Toplevel(root)
    win.title("Добавить категорию")
    win.geometry("300x150")

    ttk.Label(win, text="Название категории:").pack(pady=10)
    entry = ttk.Entry(win)
    entry.pack()

    def save():
        try:
            new_id = add_category(entry.get())
            refresh_categories()
            messagebox.showinfo("Успех", f"Категория создана (ID={new_id})")
            win.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    ttk.Button(win, text="Сохранить", command=save).pack(pady=10)


def add_material_window():
    win = tk.Toplevel(root)
    win.title("Добавить материал")
    win.geometry("400x350")

    labels = ["Название", "Единица (шт/кг)", "Количество", "Мин. остаток", "Категория"]

    widgets = []

    for label in labels[:-1]:
        ttk.Label(win, text=label).pack(anchor="w", padx=15, pady=5)
        entry = ttk.Entry(win)
        entry.pack(fill="x", padx=15)
        widgets.append(entry)

    ttk.Label(win, text="Категория").pack(anchor="w", padx=15, pady=5)

    global combobox_category
    combobox_category = ttk.Combobox(win, values=category_names, state="readonly")
    combobox_category.pack(fill="x", padx=15)

    if category_names:
        combobox_category.current(0)

    def save():
        try:
            name = widgets[0].get()
            unit = widgets[1].get()
            qty = int(widgets[2].get())
            min_q = int(widgets[3].get())

            cat_name = combobox_category.get()
            category_id = next(cid for cid, cname in categories_list if cname == cat_name)

            new_id = add_material(name, unit, qty, min_q, category_id)

            add_log(CURRENT_USER_ID, "Добавление материала", f"{name}, qty={qty}")

            refresh_table()
            messagebox.showinfo("Успех", f"Материал создан (ID={new_id})")
            win.destroy()

        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    ttk.Button(win, text="Сохранить", command=save).pack(pady=15)


def change_quantity_window(operation):
    win = tk.Toplevel(root)
    win.title(operation)
    win.geometry("300x180")

    ttk.Label(win, text="ID материала:").pack(pady=5)
    e_id = ttk.Entry(win)
    e_id.pack()

    ttk.Label(win, text="Количество:").pack(pady=5)
    e_qty = ttk.Entry(win)
    e_qty.pack()

    def save():
        try:
            material_id = int(e_id.get())
            amount = int(e_qty.get())

            if operation == "Приход":
                increase_material(CURRENT_USER_ID, material_id, amount)
            else:
                decrease_material(CURRENT_USER_ID, material_id, amount)

            refresh_table()
            win.destroy()
            messagebox.showinfo("Готово", f"{operation} выполнен")

        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    ttk.Button(win, text="OK", command=save).pack(pady=15)


def open_transactions_window():
    win = tk.Toplevel(root)
    win.title("История операций")
    win.geometry("900x400")

    table = ttk.Treeview(
        win,
        columns=("ID", "Материал", "Тип", "Кол-во", "Комментарий", "Дата"),
        show="headings"
    )
    table.pack(fill=tk.BOTH, expand=True)

    for col in ("ID", "Материал", "Тип", "Кол-во", "Комментарий", "Дата"):
        table.heading(col, text=col)
        table.column(col, width=150)

    for row in load_transactions():
        table.insert("", tk.END, values=row)



# MAIN WINDOW

refresh_categories()

root = tk.Tk()
root.title("Учёт расходных материалов")
root.geometry("950x600")

apply_style(root)


table_frame = ttk.Frame(root, padding=10)
table_frame.pack(fill=tk.BOTH, expand=True)

tree = ttk.Treeview(
    table_frame,
    columns=("ID", "Название", "Ед.", "Количество", "Категория"),
    show="headings",
    height=12
)
tree.pack(fill=tk.BOTH, expand=True)

for col in ("ID", "Название", "Ед.", "Количество", "Категория"):
    tree.heading(col, text=col)
    tree.column(col, width=150)

refresh_table()

# Кнопки
frame = ttk.Frame(root)
frame.pack(pady=10)

ttk.Button(frame, text="Добавить категорию", command=add_category_window).grid(row=0, column=0, padx=5)
ttk.Button(frame, text="Удалить категорию", command=delete_category_window).grid(row=0, column=1, padx=5)

ttk.Button(frame, text="Добавить материал", command=add_material_window).grid(row=0, column=2, padx=5)
ttk.Button(frame, text="Удалить материал", command=delete_material_window).grid(row=0, column=3, padx=5)

ttk.Button(frame, text="Приход", command=lambda: change_quantity_window("Приход")).grid(row=0, column=4, padx=5)
ttk.Button(frame, text="Расход", command=lambda: change_quantity_window("Расход")).grid(row=0, column=5, padx=5)

ttk.Button(frame, text="История операций", command=open_transactions_window).grid(row=0, column=6, padx=5)
ttk.Button(frame, text="Обновить", command=refresh_table).grid(row=0, column=7, padx=5)

root.mainloop()
