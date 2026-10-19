export async function loadItems(): Promise<unknown> {
  return (await fetch("/api/items")).json();
}

export async function loadUser(id: string): Promise<unknown> {
  return (await fetch(`/api/users/${id}`)).json();
}

export async function loadOrders(): Promise<unknown> {
  return (await fetch("https://api.example.test/v1/orders?limit=5")).json();
}
