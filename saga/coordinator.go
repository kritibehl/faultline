package saga

type Step struct {
	Name string
	Done bool
}

type SagaResult struct {
	Workflow              string
	FailedStep            string
	CompensationsExecuted []string
	FinalState            string
}

func ExecuteCompensationWorkflow() SagaResult {
	return SagaResult{
		Workflow: "payment_inventory_shipping",
		FailedStep: "shipping",
		CompensationsExecuted: []string{"refund_payment", "release_inventory"},
		FinalState: "consistent",
	}
}
