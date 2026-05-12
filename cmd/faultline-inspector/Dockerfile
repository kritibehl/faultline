FROM golang:1.22-alpine AS build
WORKDIR /app
COPY cmd/faultline-inspector/go.mod cmd/faultline-inspector/go.sum ./
RUN go mod download
COPY cmd/faultline-inspector/main.go ./
RUN go build -o faultline-inspector .

FROM alpine:3.20
WORKDIR /app
COPY --from=build /app/faultline-inspector .
ENV PORT=8088
EXPOSE 8088
CMD ["./faultline-inspector"]
