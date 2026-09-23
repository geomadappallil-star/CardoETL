const fs = require('fs');
const path = require('path');
const { Client } = require('pg');

const JSON_PATH = '/home/jeo/.gemini/antigravity/scratch/CardoETL/data/spices_board_small_cardamom_full.json';
const DB_URL = "postgresql://postgres.thgczdlokjrxzakncgwd:Madappallil@1997@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres?sslmode=disable";

async function main() {
  console.log("==================================================");
  console.log("CARDO BOARD — SMALL CARDAMOM FULL DATA INGESTION");
  console.log("==================================================");

  if (!fs.existsSync(JSON_PATH)) {
    throw new Error(`Data file not found at ${JSON_PATH}`);
  }

  const raw = fs.readFileSync(JSON_PATH, 'utf-8');
  const records = JSON.parse(raw);
  console.log(`Loaded ${records.length} verified records from JSON.`);

  const client = new Client({ connectionString: DB_URL });
  console.log("Connecting to Supabase PostgreSQL pooler...");
  await client.connect();
  console.log("Connected successfully!");

  // 1. Current State
  const prevCounts = await client.query(`
    SELECT spice_id, count(*) as count 
    FROM fact_price 
    GROUP BY spice_id 
    ORDER BY spice_id
  `);
  console.log("Previous counts in fact_price by spice_id:", prevCounts.rows);

  // 2. Clear old Small Cardamom records
  console.log("\nDeleting previous cardamom records (spice_id = 1)...");
  const delRes = await client.query("DELETE FROM fact_price WHERE spice_id = 1");
  console.log(`Deleted ${delRes.rowCount} previous cardamom records.`);

  // 3. Batch Ingest
  console.log("\nIngesting 5,806 verified auction records in batches...");
  const BATCH_SIZE = 250;
  let inserted = 0;

  for (let i = 0; i < records.length; i += BATCH_SIZE) {
    const batch = records.slice(i, i + BATCH_SIZE);
    const valuePlaceholders = [];
    const queryParams = [];

    batch.forEach((r, idx) => {
      const offset = idx * 18;
      valuePlaceholders.push(
        `($${offset + 1}, $${offset + 2}, $${offset + 3}, $${offset + 4}, $${offset + 5}, $${offset + 6}, $${offset + 7}, $${offset + 8}, $${offset + 9}, $${offset + 10}, $${offset + 11}, $${offset + 12}, $${offset + 13}, $${offset + 14}, $${offset + 15}, $${offset + 16}, $${offset + 17}, $${offset + 18})`
      );
      queryParams.push(
        r.spice_id || 1,
        r.date,
        r.country_id || 1,
        r.region_id,
        r.market_id,
        r.seller_or_auctioneer,
        r.price_type || 'AUCTION',
        r.min_price,
        r.max_price,
        r.avg_price,
        r.currency || 'INR',
        r.unit || 'INR/kg',
        r.quantity,
        r.quantity_sold,
        r.quantity_unit || 'kg',
        r.source_id || 1,
        r.source_record_id,
        r.quality_status || 'VERIFIED'
      );
    });

    const insertQuery = `
      INSERT INTO fact_price (
        spice_id, date, country_id, region_id, market_id,
        seller_or_auctioneer, price_type, min_price, max_price, avg_price,
        currency, unit, quantity, quantity_sold, quantity_unit,
        source_id, source_record_id, quality_status
      ) VALUES ${valuePlaceholders.join(', ')}
    `;

    await client.query(insertQuery, queryParams);
    inserted += batch.length;
    process.stdout.write(`\r  > Ingested ${inserted} / ${records.length} records (${Math.round((inserted / records.length) * 100)}%)`);
  }

  console.log("\n\nAll records ingested successfully!");

  // 4. Verification Queries
  console.log("\n--- Verification Queries ---");
  const newCounts = await client.query(`
    SELECT spice_id, count(*) as count, min(date) as min_date, max(date) as max_date, round(avg(avg_price), 2) as mean_avg_price 
    FROM fact_price 
    GROUP BY spice_id 
    ORDER BY spice_id
  `);
  console.table(newCounts.rows);

  const topRecent = await client.query(`
    SELECT date, seller_or_auctioneer, avg_price, min_price, max_price, quantity as arrivals_kg, quantity_sold 
    FROM fact_price 
    WHERE spice_id = 1 
    ORDER BY date DESC, id DESC 
    LIMIT 10
  `);
  console.log("\nTop 10 Recent Cardamom Records:");
  console.table(topRecent.rows);

  await client.end();
  console.log("Database connection closed.");
}

main().catch(err => {
  console.error("Ingestion failed:", err);
  process.exit(1);
});
