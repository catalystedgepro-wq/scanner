const url = process.argv[2];

if (!url) {
  console.error("missing_url");
  process.exit(1);
}

try {
  const response = await fetch(url);
  const body = await response.text();
  console.log(response.status);
  console.log(body);
} catch (error) {
  console.error(String(error));
  process.exit(1);
}
