package faultline

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type SubmitRequest struct {
	JobPayload     map[string]any `json:"job_payload"`
	IdempotencyKey string         `json:"idempotency_key,omitempty"`
	Queue          string         `json:"queue,omitempty"`
	TenantID       string         `json:"tenant_id,omitempty"`
}

type SubmitResponse struct {
	JobID    string `json:"job_id"`
	State    string `json:"state"`
	Accepted bool   `json:"accepted"`
}

type ClaimRequest struct {
	WorkerID  string `json:"worker_id"`
	BatchSize int    `json:"batch_size"`
	Queue     string `json:"queue,omitempty"`
	TenantID  string `json:"tenant_id,omitempty"`
}

type CompleteRequest struct {
	JobID        string         `json:"job_id"`
	FencingToken int            `json:"fencing_token"`
	Result       map[string]any `json:"result,omitempty"`
}

type Client struct {
	BaseURL string
	HTTP    *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{
		BaseURL: baseURL,
		HTTP:    &http.Client{Timeout: 10 * time.Second},
	}
}

func (c *Client) Submit(req SubmitRequest) (*SubmitResponse, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	resp, err := c.HTTP.Post(fmt.Sprintf("%s/v1/jobs", c.BaseURL), "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var out SubmitResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *Client) Claim(req ClaimRequest) (map[string]any, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	resp, err := c.HTTP.Post(fmt.Sprintf("%s/v1/jobs/claim", c.BaseURL), "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}

func (c *Client) Complete(req CompleteRequest) (map[string]any, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	resp, err := c.HTTP.Post(fmt.Sprintf("%s/v1/jobs/complete", c.BaseURL), "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}
