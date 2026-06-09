// Command datastore-mcp is a small read-only Model Context Protocol (MCP)
// server over a Postgres "analytic data store", exposed via the Streamable
// HTTP transport so the Coder AI Gateway can inject and govern its tools.
//
// It is intentionally minimal and read-only: it connects as a least-privilege
// Postgres role, rejects any statement that is not a single SELECT/WITH query,
// runs queries inside a read-only transaction with a statement timeout, and
// caps the number of returned rows. It does not validate the inbound
// Authorization header; the AI Gateway attaches the user's external-auth
// token and records every tool call (injected=true, server_url) for
// governance. See deploy/datastore-mcp/README.md.
package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log"
	"os"
	"regexp"
	"strings"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
)

const (
	maxRows      = 200
	queryTimeout = 8 * time.Second
)

// selectOnly matches a statement whose first keyword is SELECT or WITH.
var selectOnly = regexp.MustCompile(`(?is)^\s*(select|with)\b`)

func main() {
	dsn := os.Getenv("DATABASE_URI")
	if dsn == "" {
		log.Fatal("DATABASE_URI is required")
	}
	addr := envOr("LISTEN_ADDR", ":8000")
	path := envOr("MCP_PATH", "/mcp")

	db, err := sql.Open("pgx", dsn)
	if err != nil {
		log.Fatalf("open db: %v", err)
	}
	db.SetMaxOpenConns(5)
	db.SetMaxIdleConns(2)
	db.SetConnMaxLifetime(5 * time.Minute)

	// The demo Postgres may start after this server. Retry the initial ping
	// so the pod becomes ready once the database is reachable.
	if err := pingWithRetry(db, 60*time.Second); err != nil {
		log.Fatalf("database not reachable: %v", err)
	}
	log.Printf("connected to data store")

	s := server.NewMCPServer(
		"usgov-datastore-mcp",
		"0.1.0",
		server.WithToolCapabilities(true),
		server.WithRecovery(),
		server.WithInstructions("Read-only access to the unclassified demo analytic data store. "+
			"Use list_tables and describe_table to discover the schema, then query with a single SELECT/WITH statement."),
	)

	s.AddTool(
		mcp.NewTool("list_tables",
			mcp.WithDescription("List tables available in the demo analytic data store (schema public), with row counts.")),
		func(ctx context.Context, _ mcp.CallToolRequest) (*mcp.CallToolResult, error) {
			const q = `SELECT table_name FROM information_schema.tables
			           WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
			           ORDER BY table_name`
			out, err := runReadOnly(ctx, db, q)
			if err != nil {
				return mcp.NewToolResultError(err.Error()), nil
			}
			return mcp.NewToolResultText(out), nil
		},
	)

	s.AddTool(
		mcp.NewTool("describe_table",
			mcp.WithDescription("Describe the columns (name and type) of a table in the demo data store."),
			mcp.WithString("table", mcp.Required(), mcp.Description("Table name in schema public."))),
		func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
			table, err := req.RequireString("table")
			if err != nil {
				return mcp.NewToolResultError(err.Error()), nil
			}
			if !isIdent(table) {
				return mcp.NewToolResultError("invalid table name"), nil
			}
			q := `SELECT column_name, data_type, is_nullable
			      FROM information_schema.columns
			      WHERE table_schema = 'public' AND table_name = '` + table + `'
			      ORDER BY ordinal_position`
			out, err := runReadOnly(ctx, db, q)
			if err != nil {
				return mcp.NewToolResultError(err.Error()), nil
			}
			return mcp.NewToolResultText(out), nil
		},
	)

	s.AddTool(
		mcp.NewTool("query",
			mcp.WithDescription("Run a single read-only SQL query (SELECT or WITH) against the demo analytic "+
				"data store and return the rows as text. Non-SELECT statements and multiple statements are rejected. "+
				"At most 200 rows are returned."),
			mcp.WithString("sql", mcp.Required(), mcp.Description("A single SELECT or WITH query."))),
		func(ctx context.Context, req mcp.CallToolRequest) (*mcp.CallToolResult, error) {
			raw, err := req.RequireString("sql")
			if err != nil {
				return mcp.NewToolResultError(err.Error()), nil
			}
			stmt, err := sanitize(raw)
			if err != nil {
				return mcp.NewToolResultError(err.Error()), nil
			}
			out, err := runReadOnly(ctx, db, stmt)
			if err != nil {
				return mcp.NewToolResultError(err.Error()), nil
			}
			return mcp.NewToolResultText(out), nil
		},
	)

	httpSrv := server.NewStreamableHTTPServer(s,
		server.WithEndpointPath(path),
		server.WithStateLess(true),
	)
	log.Printf("datastore MCP (streamable HTTP) listening on %s%s", addr, path)
	if err := httpSrv.Start(addr); err != nil {
		log.Fatalf("server: %v", err)
	}
}

// sanitize enforces the single read-only statement policy.
func sanitize(raw string) (string, error) {
	stmt := strings.TrimSpace(raw)
	stmt = strings.TrimSuffix(stmt, ";")
	if stmt == "" {
		return "", errors.New("empty query")
	}
	if strings.Contains(stmt, ";") {
		return "", errors.New("only a single statement is allowed")
	}
	if !selectOnly.MatchString(stmt) {
		return "", errors.New("only SELECT or WITH queries are allowed")
	}
	return stmt, nil
}

// runReadOnly executes a query inside a read-only transaction with a statement
// timeout and renders the result as a compact text table.
func runReadOnly(ctx context.Context, db *sql.DB, query string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, queryTimeout)
	defer cancel()

	tx, err := db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return "", err
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, "SET LOCAL statement_timeout = '8s'"); err != nil {
		return "", err
	}

	rows, err := tx.QueryContext(ctx, query)
	if err != nil {
		return "", err
	}
	defer rows.Close()

	cols, err := rows.Columns()
	if err != nil {
		return "", err
	}

	var b strings.Builder
	b.WriteString(strings.Join(cols, " | "))
	b.WriteString("\n")

	vals := make([]any, len(cols))
	ptrs := make([]any, len(cols))
	for i := range vals {
		ptrs[i] = &vals[i]
	}

	n := 0
	truncated := false
	for rows.Next() {
		if n >= maxRows {
			truncated = true
			break
		}
		if err := rows.Scan(ptrs...); err != nil {
			return "", err
		}
		cells := make([]string, len(cols))
		for i, v := range vals {
			cells[i] = render(v)
		}
		b.WriteString(strings.Join(cells, " | "))
		b.WriteString("\n")
		n++
	}
	if err := rows.Err(); err != nil {
		return "", err
	}

	b.WriteString(fmt.Sprintf("\n(%d row(s)", n))
	if truncated {
		b.WriteString(fmt.Sprintf(", truncated at %d", maxRows))
	}
	b.WriteString(")")
	return b.String(), nil
}

func render(v any) string {
	switch t := v.(type) {
	case nil:
		return ""
	case []byte:
		return string(t)
	case time.Time:
		return t.Format(time.RFC3339)
	case string:
		return t
	default:
		return fmt.Sprintf("%v", t)
	}
}

var identRe = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

func isIdent(s string) bool { return identRe.MatchString(s) }

func envOr(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func pingWithRetry(db *sql.DB, total time.Duration) error {
	deadline := time.Now().Add(total)
	var last error
	for time.Now().Before(deadline) {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		err := db.PingContext(ctx)
		cancel()
		if err == nil {
			return nil
		}
		last = err
		time.Sleep(2 * time.Second)
	}
	return last
}
